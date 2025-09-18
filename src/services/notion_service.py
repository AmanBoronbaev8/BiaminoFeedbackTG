"""Notion API service for fetching tasks and workers."""
import re
import asyncio
from typing import List, Dict, Set
import aiohttp
from loguru import logger

from ..config_data import Config


class NotionService:
    """Service for working with Notion API."""
    
    def __init__(self, config: Config):
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
        async with session.get(url, headers=self.headers) as resp:
            resp.raise_for_status()
            return await resp.json()
            
    async def get_worker_names_from_relation_list(self, session: aiohttp.ClientSession, rel_list: List[Dict]) -> List[str]:
        """Extract worker names from relation list."""
        names = []
        for rel in rel_list:
            wid = rel.get('id')
            if wid:
                try:
                    wpage = await self.get_page(session, wid)
                    props = wpage.get('properties', {})
                    
                    # Find title property in worker table
                    worker_name = None
                    for prop_name, prop in props.items():
                        if prop.get('type') == 'title':
                            title_arr = prop.get('title', [])
                            worker_name = ''.join([t.get('plain_text', '') for t in title_arr])
                            break
                    
                    if worker_name:
                        names.append(worker_name)
                    else:
                        names.append("(без имени)")
                        
                except Exception as e:
                    logger.error(f"Error getting worker page {wid}: {e}")
                    names.append(f"(ошибка {wid})")
                    
        return names
        
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
            
            # Query the database
            query_url = f'https://api.notion.com/v1/data_sources/{data_source_id}/query'
            payload = {}
            
            async with session.post(query_url, headers=self.headers, json=payload) as query_resp:
                query_resp.raise_for_status()
                data = await query_resp.json()
                
            tasks = []
            for page in data.get('results', []):
                properties = page.get('properties', {})
                
                task_name = properties.get('Task name', {}).get('title', [{}])[0].get('plain_text', '')
                due_date = properties.get('Срок выполнения', {}).get('date', {}).get('start', '')
                status = properties.get('Статус', {}).get('select', {}).get('name', '')
                
                # Only process non-completed tasks
                if status != 'Done':
                    worker_property = properties.get('👤 Воркер', {})
                    worker_names = []
                    if worker_property.get('relation'):
                        rel_list = worker_property.get('relation', [])
                        worker_names = await self.get_worker_names_from_relation_list(session, rel_list)
                    
                    if worker_names:
                        for worker_name in worker_names:
                            tasks.append({
                                'task_name': task_name,
                                'due_date': due_date,
                                'status': status,
                                'worker_name': worker_name,
                                'database_id': database_id
                            })
                            
            logger.info(f"Retrieved {len(tasks)} active tasks from database {database_id}")
            return tasks
            
        except Exception as e:
            logger.error(f"Error getting tasks from database {database_id}: {e}")
            return []
            
    async def get_all_tasks(self) -> List[Dict]:
        """Get all tasks from both Notion databases."""
        all_tasks = []
        
        async with aiohttp.ClientSession() as session:
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
    def clean_worker_name(worker_name: str) -> tuple[str, str]:
        """Clean worker name and extract first and last name."""
        # Remove special characters and extra spaces
        cleaned = re.sub(r'[^\w\s]', ' ', worker_name)
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