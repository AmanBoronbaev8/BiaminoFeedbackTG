"""Task synchronization service between Notion and Google Sheets."""
import re
import uuid
from datetime import datetime
from typing import List, Dict, Set
from loguru import logger

from .notion_service import NotionService
from .sheets_service import GoogleSheetsService
from ..config_data import Config


class TaskSyncService:
    """Service for synchronizing tasks between Notion and Google Sheets."""
    
    def __init__(self, notion_service: NotionService, sheets_service: GoogleSheetsService, config: Config):
        self.notion_service = notion_service
        self.sheets_service = sheets_service
        self.config = config
        
    async def sync_tasks_from_notion(self) -> Dict[str, int]:
        """Sync tasks from Notion to Google Sheets."""
        logger.info("Starting task synchronization from Notion to Google Sheets")
        
        stats = {
            'total_tasks': 0,
            'processed_workers': 0,
            'updated_sheets': 0,
            'errors': 0
        }
        
        try:
            # Get all tasks from Notion
            notion_tasks = await self.notion_service.get_all_tasks()
            stats['total_tasks'] = len(notion_tasks)
            
            if not notion_tasks:
                logger.info("No tasks found in Notion databases")
                return stats
                
            # Group tasks by worker
            tasks_by_worker = {}
            for task in notion_tasks:
                worker_name = task['worker_name']
                if worker_name not in tasks_by_worker:
                    tasks_by_worker[worker_name] = []
                tasks_by_worker[worker_name].append(task)
                
            logger.info(f"Found tasks for {len(tasks_by_worker)} workers")
            stats['processed_workers'] = len(tasks_by_worker)
            
            # Process each worker
            for worker_name, worker_tasks in tasks_by_worker.items():
                try:
                    await self._sync_worker_tasks(worker_name, worker_tasks)
                    stats['updated_sheets'] += 1
                except Exception as e:
                    logger.error(f"Error syncing tasks for worker {worker_name}: {e}")
                    stats['errors'] += 1
                    
            logger.info(f"Task synchronization completed: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error in task synchronization: {e}")
            stats['errors'] += 1
            return stats
            
    async def _sync_worker_tasks(self, worker_name: str, tasks: List[Dict]) -> None:
        """Sync tasks for a specific worker."""
        logger.debug(f"Syncing {len(tasks)} tasks for worker: {worker_name}")
        
        # Clean worker name and extract first/last name
        first_name, last_name = self.notion_service.clean_worker_name(worker_name)
        
        if not first_name or not last_name:
            logger.warning(f"Could not extract valid first/last name from: {worker_name}")
            return
            
        logger.debug(f"Cleaned name: {first_name} {last_name}")
        
        # Find employee in team sheet
        employee_data = await self.sheets_service.get_employee_data(last_name, first_name)
        if not employee_data:
            logger.warning(f"Employee not found in team sheet: {last_name} {first_name}")
            return
            
        employee_id = employee_data.get(self.config.team_id_col)
        if not employee_id:
            logger.warning(f"Employee ID not found for: {last_name} {first_name}")
            return
            
        logger.debug(f"Found employee ID: {employee_id}")
        
        # Try to access employee sheet - if it doesn't exist, skip this worker
        try:
            employee_sheet = self.sheets_service.sh.worksheet(employee_id)
        except Exception as sheet_error:
            logger.warning(f"Cannot access employee sheet '{employee_id}': {sheet_error}")
            return
        
        # Get existing tasks to avoid duplicates
        existing_tasks = await self._get_existing_notion_tasks(employee_id)
        logger.debug(f"Found {len(existing_tasks)} existing Notion tasks for {employee_id}")
        
        # Filter tasks to avoid duplicates
        tasks_to_add = []
        for task in tasks:
            task_name = task['task_name']
            normalized_name = self._normalize_task_name(task_name)
            
            if normalized_name in existing_tasks:
                logger.debug(f"Task already exists, skipping: {task_name}")
                continue
                
            tasks_to_add.append(task)
        
        if not tasks_to_add:
            logger.info(f"No new tasks to add for employee {employee_id}")
            return
            
        logger.info(f"Adding {len(tasks_to_add)} new tasks for employee {employee_id}")
        
        # Add new tasks from Notion
        new_tasks_added = 0
        for task in tasks_to_add:
            task_name = task['task_name']
            
            # Create unique task ID based on task name and database
            task_id = self._generate_task_id(task_name, task['database_id'])
            
            # Add task to sheet
            success = await self._add_task_to_sheet(
                employee_sheet, 
                task_id, 
                task_name, 
                task['due_date']
            )
            
            if success:
                new_tasks_added += 1
                logger.debug(f"Added task: {task_id} - {task_name}")
            else:
                logger.error(f"Failed to add task: {task_id}")
                
        logger.info(f"Successfully added {new_tasks_added} new tasks for employee {employee_id}")
        
    async def _get_existing_notion_tasks(self, employee_id: str) -> Set[str]:
        """Get set of existing Notion task identifiers to avoid duplicates."""
        try:
            employee_sheet = self.sheets_service.sh.worksheet(employee_id)
            
            # Get tasks table range
            start_row = self.config.tasks_table_start_row
            start_col = self.config.tasks_table_start_col
            end_col = chr(ord(start_col) + 4)  # A-E = 5 columns
            
            range_name = f"{start_col}{start_row}:{end_col}"
            tasks_values = employee_sheet.get(range_name)
            
            if not tasks_values or len(tasks_values) <= 1:
                return set()
                
            # Find column indices
            header_row = tasks_values[0]
            task_id_col = task_name_col = None
            for i, header in enumerate(header_row):
                if header == self.config.tasks_id_col:
                    task_id_col = i
                elif header == self.config.tasks_task_col:
                    task_name_col = i
                    
            if task_id_col is None or task_name_col is None:
                return set()
                
            # Extract existing Notion task identifiers for deduplication
            existing_identifiers = set()
            for row in tasks_values[1:]:
                if (len(row) > max(task_id_col, task_name_col) and 
                    row[task_id_col].strip() and 
                    row[task_name_col].strip()):
                    
                    task_id = row[task_id_col].strip()
                    task_name = row[task_name_col].strip()
                    
                    # Check if this is a Notion-generated task
                    if 'NOTION_' in task_id:
                        # Create identifier from normalized task name for exact matching
                        normalized_name = self._normalize_task_name(task_name)
                        existing_identifiers.add(normalized_name)
                        
            logger.debug(f"Found {len(existing_identifiers)} existing Notion tasks for {employee_id}")
            return existing_identifiers
            
        except Exception as e:
            logger.error(f"Error getting existing tasks for {employee_id}: {e}")
            return set()
            
    async def _add_task_to_sheet(self, employee_sheet, task_id: str, task_name: str, due_date: str) -> bool:
        """Add a single task to employee sheet."""
        try:
            today = datetime.now().strftime("%d.%m.%Y")
            
            # Get tasks table range
            start_row = self.config.tasks_table_start_row
            start_col = self.config.tasks_table_start_col
            end_col = chr(ord(start_col) + 4)  # A-E = 5 columns
            
            range_name = f"{start_col}{start_row}:{end_col}"
            tasks_values = employee_sheet.get(range_name)
            
            if not tasks_values:
                # Skip if no data exists (no sheet or empty sheet)
                logger.warning(f"No tasks table found for employee {employee_sheet.title}, skipping task addition")
                return False
                
            # Find the next empty row
            next_row = start_row + len(tasks_values)
            
            # Create new task row
            new_task_row = [
                today,           # Date
                task_id,         # Task ID
                task_name,       # Task
                due_date,        # Deadline
                ""               # Completed (empty = not completed)
            ]
            
            # Update the row
            update_range = f'{start_col}{next_row}:{end_col}{next_row}'
            employee_sheet.update(update_range, [new_task_row])
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding task to sheet: {e}")
            return False
            
    def _normalize_task_name(self, task_name: str) -> str:
        """Normalize task name for consistent comparison."""
        if not task_name:
            return ""
        
        # Normalize: strip whitespace, convert to lowercase, remove extra spaces
        normalized = re.sub(r'\s+', ' ', task_name.strip().lower())
        return normalized
        
    def _generate_task_id(self, task_name: str, database_id: str) -> str:
        """Generate unique task ID for Notion tasks."""
        # Use first 8 chars of database ID + shortened task name + random suffix
        db_prefix = database_id[:8]
        task_prefix = re.sub(r'[^\w]', '', task_name)[:20]  # Clean and limit to 20 chars
        random_suffix = str(uuid.uuid4())[:8]
        
        return f"NOTION_{db_prefix}_{task_prefix}_{random_suffix}".upper()