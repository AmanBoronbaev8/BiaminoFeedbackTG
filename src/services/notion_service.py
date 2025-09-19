"""Notion API service for fetching tasks and workers."""
import re
import asyncio
from typing import List, Dict, Set, Optional, Tuple
import aiohttp
from loguru import logger

from ..config_data import Config


class NotionService:
    """Service for working with Notion API."""
    
    def __init__(self, config: Config) -> None:
        self.config = config
        self.api_token = config.notion_api_token.get_secret_value()
        self.database_ids = [config.notion_database_id_1, config.notion_database_id_2]
        self.headers = {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json',
            'Notion-Version': '2025-09-03'
        }
        
    async def get_page(self, session: aiohttp.ClientSession, page_id: str) -> Dict:
        """Get page by page_id and return its JSON."""
        url = f'https://api.notion.com/v1/pages/{page_id}'
        try:
            async with session.get(url, headers=self.headers) as resp:
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error getting page {page_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting page {page_id}: {e}")
            raise
            
    async def get_worker_names_from_relation_list(
        self, 
        session: aiohttp.ClientSession, 
        rel_list: List[Dict]
    ) -> List[str]:
        """Extract worker names from relation list."""
        if not rel_list:
            return []
            
        names = []
        for rel in rel_list:
            wid = rel.get('id')
            if not wid:
                continue
                
            try:
                wpage = await self.get_page(session, wid)
                props = wpage.get('properties', {})
                
                # Find title property in worker table
                worker_name = self._extract_title_from_properties(props)
                
                if worker_name:
                    names.append(worker_name)
                else:
                    names.append("(без имени)")
                    logger.warning(f"Worker {wid} has no title")
                    
            except Exception as e:
                logger.error(f"Error getting worker page {wid}: {e}")
                names.append(f"(ошибка {wid})")
                
        return names
    
    def _extract_title_from_properties(self, props: Dict) -> Optional[str]:
        """Extract title from properties."""
        for prop_name, prop in props.items():
            if prop.get('type') == 'title':
                title_arr = prop.get('title', [])
                return ''.join([t.get('plain_text', '') for t in title_arr]).strip()
        return None
        
    async def get_tasks_from_database(self, session: aiohttp.ClientSession, database_id: str) -> List[Dict]:
        """Get tasks from a specific Notion database."""
        try:
            # Get database info to find data source
            database_url = f'https://api.notion.com/v1/databases/{database_id}'
            
            async with session.get(database_url, headers=self.headers) as db_resp:
                db_resp.raise_for_status()
                db_data = await db_resp.json()
                
            data_sources = db_data.get('data_sources', [])
            if not data_sources:
                logger.warning(f'No data sources found in database {database_id}')
                return []
                
            data_source_id = data_sources[0].get('id')
            if not data_source_id:
                logger.warning(f'Invalid data source in database {database_id}')
                return []
            
            # Query the database with better error handling
            tasks = await self._query_database(session, data_source_id, database_id)
            
            logger.info(f"Retrieved {len(tasks)} active tasks from database {database_id}")
            return tasks
            
        except Exception as e:
            logger.error(f"Error getting tasks from database {database_id}: {e}")
            return []
    
    async def _query_database(
        self, 
        session: aiohttp.ClientSession, 
        data_source_id: str, 
        database_id: str
    ) -> List[Dict]:
        """Query database and process results."""
        query_url = f'https://api.notion.com/v1/data_sources/{data_source_id}/query'
        payload = {}
        
        async with session.post(query_url, headers=self.headers, json=payload) as query_resp:
            query_resp.raise_for_status()
            data = await query_resp.json()
            
        tasks = []
        for page in data.get('results', []):
            task = await self._process_page_to_task(session, page, database_id)
            if task:
                tasks.extend(task)
                
        return tasks
    
    async def _process_page_to_task(
        self, 
        session: aiohttp.ClientSession, 
        page: Dict, 
        database_id: str
    ) -> List[Dict]:
        """Process a single page into task(s)."""
        properties = page.get('properties', {})
        
        # Extract basic task info
        task_name = self._extract_text_property(properties, 'Task name')
        due_date = self._extract_date_property(properties, 'Срок выполнения')
        status = self._extract_select_property(properties, 'Статус')
        
        # Skip completed tasks
        if status == 'Done':
            return []
        
        # Validate required fields
        if not task_name or not task_name.strip():
            logger.warning(f"Task from database {database_id} has empty name, skipping")
            return []
            
        # Get worker names
        worker_property = properties.get('👤 Воркер', {})
        worker_names = []
        
        if worker_property.get('relation'):
            rel_list = worker_property.get('relation', [])
            try:
                worker_names = await self.get_worker_names_from_relation_list(session, rel_list)
            except Exception as e:
                logger.error(f"Error getting worker names for task '{task_name}': {e}")
                return []
        
        # Create tasks for each worker
        tasks = []
        if worker_names:
            for worker_name in worker_names:
                if worker_name and worker_name.strip():  # Ensure valid worker name
                    tasks.append({
                        'task_name': task_name.strip(),
                        'due_date': due_date,
                        'status': status,
                        'worker_name': worker_name.strip(),
                        'database_id': database_id,
                        'page_id': page.get('id', '')  # Add page ID for better tracking
                    })
        else:
            logger.debug(f"Task '{task_name}' has no assigned workers")
            
        return tasks
    
    def _extract_text_property(self, properties: Dict, prop_name: str) -> str:
        """Extract text from title property."""
        prop = properties.get(prop_name, {})
        title_arr = prop.get('title', [])
        return ''.join([t.get('plain_text', '') for t in title_arr])
    
    def _extract_date_property(self, properties: Dict, prop_name: str) -> str:
        """Extract date from date property."""
        prop = properties.get(prop_name, {})
        return prop.get('date', {}).get('start', '')
    
    def _extract_select_property(self, properties: Dict, prop_name: str) -> str:
        """Extract name from select property."""
        prop = properties.get(prop_name, {})
        return prop.get('select', {}).get('name', '')
            
    async def get_all_tasks(self) -> List[Dict]:
        """Get all tasks from both Notion databases."""
        all_tasks = []
        
        timeout = aiohttp.ClientTimeout(total=30)  # Add timeout
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Process both databases in parallel
            tasks_results = await asyncio.gather(
                *[self.get_tasks_from_database(session, db_id) for db_id in self.database_ids],
                return_exceptions=True
            )
            
            for i, result in enumerate(tasks_results):
                if isinstance(result, Exception):
                    logger.error(f"Error processing database {self.database_ids[i]}: {result}")
                else:
                    all_tasks.extend(result)
                    
        logger.info(f"Retrieved total {len(all_tasks)} active tasks from all databases")
        return all_tasks
        
    @staticmethod
    def clean_worker_name(worker_name: str) -> Tuple[str, str]:
        """Clean worker name and extract first and last name."""
        if not worker_name or not isinstance(worker_name, str):
            return "", ""
            
        # Remove special characters and extra spaces
        cleaned = re.sub(r'[^\w\s\-]', ' ', worker_name)  # Allow hyphens in names
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        # Split into parts
        parts = cleaned.split()
        if len(parts) >= 2:
            # Assume first part is first name, second part is last name
            first_name = parts[0]
            last_name = parts[1]
        elif len(parts) == 1:
            # Only one name provided
            first_name = parts[0]
            last_name = ""
        else:
            # No valid name
            first_name = ""
            last_name = ""
            
        return first_name, last_name