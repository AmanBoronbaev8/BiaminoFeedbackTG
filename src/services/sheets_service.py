"""Google Sheets service module."""
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Set
from loguru import logger
import gspread
from google.oauth2.service_account import Credentials

from ..utils.telegram_utils import parse_telegram_ids
from ..config_data import Config


class GoogleSheetsService:
    """Service for working with Google Sheets."""
    
    def __init__(self, service_account_file: str, spreadsheet_id: str, config: Config):
        self.service_account_file = service_account_file
        self.spreadsheet_id = spreadsheet_id
        self.config = config
        self.gc = None
        self.sh = None
        # Cache for employee data to avoid repeated API calls
        self._employees_cache = None
        self._cache_timestamp = None
        self._cache_ttl = 300  # 5 minutes cache TTL
        
    async def initialize(self) -> None:
        """Initialize Google Sheets connection."""
        try:
            # Define required scopes
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive.metadata.readonly",
            ]
            
            # Create credentials and authorize
            creds = Credentials.from_service_account_file(
                self.service_account_file, 
                scopes=scopes
            )
            self.gc = gspread.authorize(creds)
            
            # Open the spreadsheet
            self.sh = self.gc.open_by_key(self.spreadsheet_id)
            logger.info(f"Successfully connected to Google Sheets: {self.spreadsheet_id}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets: {e}")
            raise
            
    async def get_employee_data(self, last_name: str, first_name: str) -> Optional[Dict]:
        """Get employee data from team sheet."""
        try:
            logger.debug(f"Getting employee data for: {last_name} {first_name}")
            team_sheet = self.sh.worksheet(self.config.team_sheet_name)
            all_values = team_sheet.get_all_values()
            
            if not all_values or len(all_values) < 2:
                logger.debug("No data found in team sheet")
                return None
                
            # Get header row and data rows
            header_row = all_values[0]
            data_rows = all_values[1:]
            
            logger.debug(f"Found {len(data_rows)} records in team sheet")
            
            # Process each data row
            for i, row in enumerate(data_rows):
                # Create record dict from header and row data
                record = {}
                for j, header in enumerate(header_row):
                    if j < len(row):
                        record[header] = row[j]
                    else:
                        record[header] = ""
                
                logger.debug(f"Record {i}: {record}")
                if (record.get(self.config.team_lastname_col, "").strip().lower() == last_name.strip().lower() and 
                    record.get(self.config.team_firstname_col, "").strip().lower() == first_name.strip().lower()):
                    logger.info(f"Found employee: {record}")
                    return record
            
            logger.warning(f"Employee not found: {last_name} {first_name}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting employee data: {e}")
            return None
            
    async def get_employee_by_telegram_id(self, telegram_id: int) -> Optional[Dict]:
        """Get employee data by TelegramID from team sheet."""
        try:
            logger.debug(f"Getting employee data for TelegramID: {telegram_id}")
            team_sheet = self.sh.worksheet(self.config.team_sheet_name)
            all_values = team_sheet.get_all_values()
            
            if not all_values or len(all_values) < 2:
                logger.debug("No data found in team sheet")
                return None
                
            # Get header row and data rows
            header_row = all_values[0]
            data_rows = all_values[1:]
            
            logger.debug(f"Found {len(data_rows)} records in team sheet")
            
            # Process each data row
            for i, row in enumerate(data_rows):
                # Create record dict from header and row data
                record = {}
                for j, header in enumerate(header_row):
                    if j < len(row):
                        record[header] = row[j]
                    else:
                        record[header] = ""
                
                stored_telegram_id = record.get(self.config.team_telegram_id_col, "")
                # Handle multiple telegram IDs separated by commas
                if stored_telegram_id:
                    telegram_ids = parse_telegram_ids(stored_telegram_id)
                    if telegram_id in telegram_ids:
                        logger.info(f"Found employee by TelegramID: {record}")
                        return record
            
            logger.warning(f"Employee not found with TelegramID: {telegram_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting employee data by TelegramID: {e}")
            return None
            
    def _is_cache_valid(self) -> bool:
        """Check if employee cache is still valid."""
        if self._employees_cache is None or self._cache_timestamp is None:
            return False
        
        current_time = datetime.now().timestamp()
        return (current_time - self._cache_timestamp) < self._cache_ttl
        
    async def _refresh_employees_cache(self) -> List[Dict]:
        """Refresh the employees cache with fresh data."""
        try:
            team_sheet = self.sh.worksheet(self.config.team_sheet_name)
            all_values = team_sheet.get_all_values()
            
            if not all_values or len(all_values) < 2:
                logger.info("No employee data found in team sheet")
                self._employees_cache = []
                self._cache_timestamp = datetime.now().timestamp()
                return []
                
            # Get header row and data rows
            header_row = all_values[0]
            data_rows = all_values[1:]
            
            # Convert to list of dictionaries
            records = []
            for row in data_rows:
                record = {}
                for j, header in enumerate(header_row):
                    if j < len(row):
                        record[header] = row[j]
                    else:
                        record[header] = ""
                records.append(record)
            
            self._employees_cache = records
            self._cache_timestamp = datetime.now().timestamp()
            
            logger.info(f"Employee cache refreshed with {len(records)} records")
            return records
            
        except Exception as e:
            logger.error(f"Error refreshing employee cache: {e}")
            self._employees_cache = []
            self._cache_timestamp = datetime.now().timestamp()
            return []
            
    async def get_all_employees_cached(self) -> List[Dict]:
        """Get all employees with caching to reduce API calls."""
        if self._is_cache_valid():
            logger.debug("Using cached employee data")
            return self._employees_cache
            
        logger.debug("Cache invalid, fetching fresh employee data")
        return await self._refresh_employees_cache()
        
    async def get_employees_with_tasks_batch(self, date: str = None) -> List[Dict]:
        """Get employees who have tasks for the specified date using batch operations."""
        if date is None:
            date = datetime.now().strftime("%d.%m.%Y")
            
        employees = await self.get_all_employees_cached()
        employees_with_tasks = []
        
        # Batch process employees to reduce individual API calls
        for employee in employees:
            employee_id = employee.get(self.config.team_id_col, "")
            if not employee_id:
                continue
                
            tasks = await self.get_employee_active_tasks(employee_id)
            if tasks:
                employee['tasks'] = tasks
                employees_with_tasks.append(employee)
                
        return employees_with_tasks
        
    async def get_employees_without_reports_batch(self, date: str = None) -> Tuple[List[str], List[Dict]]:
        """Get employees without reports using cached data and batch processing."""
        if date is None:
            date = datetime.now().strftime("%d.%m.%Y")
            
        employees = await self.get_all_employees_cached()
        employees_without_reports = []
        employees_with_telegram = []
        
        for employee in employees:
            employee_id = employee.get(self.config.team_id_col, "")
            if not employee_id:
                continue
                
            has_report = await self.check_report_submitted(employee_id, date)
            if not has_report:
                employees_without_reports.append(employee_id)
                # Only include employees with valid TelegramID for messaging
                telegram_ids = parse_telegram_ids(employee.get(self.config.team_telegram_id_col))
                if telegram_ids:
                    employees_with_telegram.append(employee)
                    
        return employees_without_reports, employees_with_telegram
            

    async def get_employee_active_tasks(self, employee_id: str) -> List[Dict]:
        """Get active (not completed) tasks for employee."""
        try:
            employee_sheet = self.sh.worksheet(employee_id)
            
            # Get raw values for tasks table (columns A-E)
            start_row = self.config.tasks_table_start_row
            start_col = self.config.tasks_table_start_col
            end_col = chr(ord(start_col) + 4)  # A-E = 5 columns
            
            # Get tasks table range
            range_name = f"{start_col}{start_row}:{end_col}"
            try:
                tasks_values = employee_sheet.get(range_name)
            except:
                return []
            
            if not tasks_values or len(tasks_values) <= 1:
                return []
                
            # Get header row for tasks table
            header_row = tasks_values[0] if tasks_values else []
            
            # Find column indices for tasks table (relative to start column)
            date_col = task_id_col = task_col = deadline_col = completed_col = None
            
            for i, header in enumerate(header_row):
                if header == self.config.tasks_date_col:
                    date_col = i
                elif header == self.config.tasks_id_col:
                    task_id_col = i
                elif header == self.config.tasks_task_col:
                    task_col = i
                elif header == self.config.tasks_deadline_col:
                    deadline_col = i
                elif header == self.config.tasks_completed_col:
                    completed_col = i
            
            if None in [date_col, task_id_col, task_col]:
                logger.warning(f"Missing required task columns in sheet {employee_id}")
                return []
            
            # Get active tasks (not completed)
            active_tasks = []
            for row in tasks_values[1:]:  # Skip header row
                if len(row) <= max(date_col, task_id_col, task_col):
                    continue
                    
                # Check if task is not completed
                is_completed = (completed_col is not None and 
                               len(row) > completed_col and 
                               row[completed_col].strip().lower() in ['да', 'yes', '1', 'true', '+'])
                
                if not is_completed and row[task_id_col].strip() and row[task_col].strip():
                    task_data = {
                        'date': row[date_col] if len(row) > date_col else '',
                        'task_id': row[task_id_col],
                        'task': row[task_col],
                        'deadline': row[deadline_col] if deadline_col and len(row) > deadline_col else '',
                    }
                    active_tasks.append(task_data)
                    
            return active_tasks
            
        except Exception as e:
            logger.error(f"Error getting active tasks for {employee_id}: {e}")
            return []
            
    async def get_tasks_without_reports_today(self, employee_id: str) -> List[Dict]:
        """Get active tasks that don't have reports for today."""
        try:
            today = datetime.now().strftime("%d.%m.%Y")
            
            # Get all active tasks
            active_tasks = await self.get_employee_active_tasks(employee_id)
            if not active_tasks:
                return []
            
            # Get existing reports for today
            existing_reports = await self.get_existing_reports_for_date(employee_id, today)
            reported_task_ids = {report.get('task_id') for report in existing_reports}
            
            # Filter out tasks that already have reports today
            tasks_without_reports = [
                task for task in active_tasks 
                if task.get('task_id') not in reported_task_ids
            ]
            
            return tasks_without_reports
            
        except Exception as e:
            logger.error(f"Error getting tasks without reports for {employee_id}: {e}")
            return []
            
    async def get_existing_reports_for_date(self, employee_id: str, date: str) -> List[Dict]:
        """Get existing reports for a specific date."""
        try:
            employee_sheet = self.sh.worksheet(employee_id)
            
            # Get reports table range (columns H-L)
            reports_start_row = self.config.reports_table_start_row
            reports_start_col = self.config.reports_table_start_col
            reports_end_col = chr(ord(reports_start_col) + 4)  # H-L = 5 columns
            reports_range = f"{reports_start_col}{reports_start_row}:{reports_end_col}"
            
            try:
                reports_values = employee_sheet.get(reports_range)
            except:
                return []
            
            if not reports_values or len(reports_values) <= 1:
                return []
                
            # Get header row for reports table
            header_row = reports_values[0]
            
            # Find column indices
            date_col = task_id_col = None
            for i, header in enumerate(header_row):
                if header == self.config.reports_date_col:
                    date_col = i
                elif header == self.config.reports_task_id_col:
                    task_id_col = i
            
            if None in [date_col, task_id_col]:
                return []
            
            # Get reports for the specified date
            reports = []
            for row in reports_values[1:]:  # Skip header row
                if (len(row) > date_col and 
                    row[date_col] == date and 
                    len(row) > task_id_col and 
                    row[task_id_col].strip()):
                    
                    report = {
                        'date': row[date_col],
                        'task_id': row[task_id_col]
                    }
                    reports.append(report)
                    
            return reports
            
        except Exception as e:
            logger.error(f"Error getting existing reports for {employee_id}: {e}")
            return []
            
    async def get_tasks_with_deadline(self, employee_id: str, deadline_date: str) -> List[Dict]:
        """Get active tasks with specific deadline date."""
        try:
            # Get active tasks
            active_tasks = await self.get_employee_active_tasks(employee_id)
            
            # Filter tasks with matching deadline
            tasks_with_deadline = [
                task for task in active_tasks 
                if task.get('deadline', '').strip() == deadline_date
            ]
            
            return tasks_with_deadline
            
        except Exception as e:
            logger.error(f"Error getting tasks with deadline for {employee_id}: {e}")
            return []
            
    async def save_daily_report(self, employee_id: str, task_id: str, feedback: str, difficulties: str, daily_report: str) -> bool:
        """Save daily report to employee's sheet reports table.
        
        Args:
            employee_id: Employee ID
            task_id: Task ID (can be empty string for general reports)
            feedback: Feedback text
            difficulties: Difficulties text
            daily_report: Daily report text
        """
        try:
            today = datetime.now().strftime("%d.%m.%Y")
            
            # Use empty string instead of None for task_id to ensure consistent handling
            task_id = task_id or ""
            
            # Get or create employee sheet
            try:
                employee_sheet = self.sh.worksheet(employee_id)
            except:
                # Create new sheet if doesn't exist
                employee_sheet = self.sh.add_worksheet(
                    title=employee_id, 
                    rows="1000", 
                    cols="15"
                )
                await self._initialize_employee_sheet(employee_sheet)
            
            # Work with reports table (columns H-L)
            reports_start_row = self.config.reports_table_start_row
            reports_start_col = self.config.reports_table_start_col
            reports_end_col = chr(ord(reports_start_col) + 4)  # H-L = 5 columns
            
            # Get reports table range
            reports_range = f"{reports_start_col}{reports_start_row}:{reports_end_col}"
            
            try:
                reports_values = employee_sheet.get(reports_range)
            except:
                # Reports table doesn't exist, create it
                await self._ensure_reports_table_exists(employee_sheet)
                reports_values = employee_sheet.get(reports_range)
            
            if not reports_values:
                await self._ensure_reports_table_exists(employee_sheet)
                reports_values = employee_sheet.get(reports_range)
                
            # Get header row for reports table
            header_row = reports_values[0] if reports_values else []
            
            # Find column indices for reports table (relative to reports start column)
            date_col = task_id_col = feedback_col = difficulties_col = daily_report_col = None
            
            for i, header in enumerate(header_row):
                if header == self.config.reports_date_col:
                    date_col = i
                elif header == self.config.reports_task_id_col:
                    task_id_col = i
                elif header == self.config.reports_feedback_col:
                    feedback_col = i
                elif header == self.config.reports_difficulties_col:
                    difficulties_col = i
                elif header == self.config.reports_daily_report_col:
                    daily_report_col = i
            
            if None in [date_col, task_id_col, feedback_col, difficulties_col, daily_report_col]:
                logger.error(f"Missing required report columns in sheet {employee_id}")
                return False
            
            # For general reports (empty task_id), always create new row
            # For task-specific reports, check for existing entry
            row_to_update = None
            if task_id:  # Only check for existing entry if task_id is not empty
                for i, row in enumerate(reports_values[1:], start=2):  # Start from row 2 (1-indexed from reports start)
                    if (len(row) > max(date_col, task_id_col) and 
                        row[date_col] == today and 
                        row[task_id_col] == task_id):
                        row_to_update = reports_start_row + i - 1  # Convert to absolute row number
                        break
                        
            if row_to_update:
                # Update existing row
                feedback_col_abs = chr(ord(reports_start_col) + feedback_col)
                daily_report_col_abs = chr(ord(reports_start_col) + daily_report_col)
                update_range = f'{feedback_col_abs}{row_to_update}:{daily_report_col_abs}{row_to_update}'
                employee_sheet.update(update_range, [[feedback, difficulties, daily_report]])
                logger.info(f"Updated existing report for {employee_id}, task: '{task_id}'")
            else:
                # Find next empty row in reports table
                next_row = reports_start_row + len(reports_values)
                
                # Create new row data
                new_row = [''] * 5  # 5 columns for reports table
                new_row[date_col] = today
                new_row[task_id_col] = task_id  # Will be empty string for general reports
                new_row[feedback_col] = feedback
                new_row[difficulties_col] = difficulties
                new_row[daily_report_col] = daily_report
                
                # Update the row
                update_range = f'{reports_start_col}{next_row}:{reports_end_col}{next_row}'
                employee_sheet.update(update_range, [new_row])
                
                if task_id:
                    logger.info(f"Saved daily report for {employee_id} task {task_id} on {today}")
                else:
                    logger.info(f"Saved general daily report for {employee_id} on {today}")
                
            return True
            
        except Exception as e:
            logger.error(f"Error saving daily report for {employee_id}: {e}")
            return False
            
    async def _initialize_employee_sheet(self, employee_sheet) -> None:
        """Initialize employee sheet with tasks and reports tables in parallel columns."""
        # Tasks table headers (columns A-E)
        tasks_headers = [
            self.config.tasks_date_col,
            self.config.tasks_id_col,
            self.config.tasks_task_col,
            self.config.tasks_deadline_col,
            self.config.tasks_completed_col
        ]
        
        # Add tasks table
        tasks_start_row = self.config.tasks_table_start_row
        tasks_start_col = self.config.tasks_table_start_col
        tasks_end_col = chr(ord(tasks_start_col) + 4)  # A-E = 5 columns
        tasks_range = f'{tasks_start_col}{tasks_start_row}:{tasks_end_col}{tasks_start_row}'
        employee_sheet.update(tasks_range, [tasks_headers])
        
        # Reports table headers (columns H-L)
        reports_headers = [
            self.config.reports_date_col,
            self.config.reports_task_id_col,
            self.config.reports_feedback_col,
            self.config.reports_difficulties_col,
            self.config.reports_daily_report_col
        ]
        
        # Add reports table
        reports_start_row = self.config.reports_table_start_row
        reports_start_col = self.config.reports_table_start_col
        reports_end_col = chr(ord(reports_start_col) + 4)  # H-L = 5 columns
        reports_range = f'{reports_start_col}{reports_start_row}:{reports_end_col}{reports_start_row}'
        employee_sheet.update(reports_range, [reports_headers])
        
    async def _ensure_reports_table_exists(self, employee_sheet) -> None:
        """Ensure reports table exists in employee sheet."""
        # Add reports table headers (columns H-L)
        reports_headers = [
            self.config.reports_date_col,
            self.config.reports_task_id_col,
            self.config.reports_feedback_col,
            self.config.reports_difficulties_col,
            self.config.reports_daily_report_col
        ]
        
        reports_start_row = self.config.reports_table_start_row
        reports_start_col = self.config.reports_table_start_col
        reports_end_col = chr(ord(reports_start_col) + 4)  # H-L = 5 columns
        reports_range = f'{reports_start_col}{reports_start_row}:{reports_end_col}{reports_start_row}'
        employee_sheet.update(reports_range, [reports_headers])
            
    async def check_report_submitted(self, employee_id: str, date: str = None) -> bool:
        """Check if employee has submitted reports for ALL incomplete tasks for the date OR has a general report.
        
        This is used for general reporting status (e.g., reminders).
        Returns True if:
        1. Reports exist for all incomplete tasks for the date, OR
        2. At least one general report (empty task_id) exists for the date
        """
        if date is None:
            date = datetime.now().strftime("%d.%m.%Y")
            
        try:
            # Get all active (incomplete) tasks for this employee
            active_tasks = await self.get_employee_active_tasks(employee_id)
            
            # Get existing reports for the date
            existing_reports = await self.get_existing_reports_for_date(employee_id, date)
            reported_task_ids = {report.get('task_id') for report in existing_reports}
            
            # Check for general reports (empty task_id)
            has_general_report = '' in reported_task_ids
            
            # If there's a general report, consider reports as submitted
            if has_general_report:
                logger.debug(f"Employee {employee_id} has general report for {date}")
                return True
            
            # If no active tasks, consider reports as "submitted"
            if not active_tasks:
                return True
                
            # Check if reports exist for all active tasks
            active_task_ids = {task.get('task_id') for task in active_tasks}
            missing_reports = active_task_ids - reported_task_ids
            
            if missing_reports:
                # There are tasks without reports
                return False
                
            # Now check if all existing reports for this date are complete
            employee_sheet = self.sh.worksheet(employee_id)
            reports_start_row = self.config.reports_table_start_row
            reports_start_col = self.config.reports_table_start_col
            reports_end_col = chr(ord(reports_start_col) + 4)
            reports_range = f"{reports_start_col}{reports_start_row}:{reports_end_col}"
            
            try:
                reports_values = employee_sheet.get(reports_range)
            except:
                return False
            
            if not reports_values or len(reports_values) <= 1:
                return False
                
            header_row = reports_values[0]
            
            # Find column indices
            date_col = task_id_col = feedback_col = difficulties_col = daily_report_col = None
            for i, header in enumerate(header_row):
                if header == self.config.reports_date_col:
                    date_col = i
                elif header == self.config.reports_task_id_col:
                    task_id_col = i
                elif header == self.config.reports_feedback_col:
                    feedback_col = i
                elif header == self.config.reports_difficulties_col:
                    difficulties_col = i
                elif header == self.config.reports_daily_report_col:
                    daily_report_col = i
            
            if None in [date_col, task_id_col, feedback_col, difficulties_col, daily_report_col]:
                return False
            
            # Check if all reports for active tasks on this date are complete
            complete_reports_for_active_tasks = set()
            for row in reports_values[1:]:  # Skip header row
                if len(row) > date_col and row[date_col] == date:
                    task_id = row[task_id_col].strip() if len(row) > task_id_col else ""
                    feedback = row[feedback_col].strip() if len(row) > feedback_col else ""
                    difficulties = row[difficulties_col].strip() if len(row) > difficulties_col else ""
                    daily_report = row[daily_report_col].strip() if len(row) > daily_report_col else ""
                    
                    # Only count reports for active tasks that are complete
                    if task_id in active_task_ids and feedback and difficulties and daily_report:
                        complete_reports_for_active_tasks.add(task_id)
            
            # Return True only if we have complete reports for ALL active tasks
            return len(complete_reports_for_active_tasks) == len(active_task_ids)
            
        except Exception as e:
            logger.error(f"Error checking report for {employee_id}: {e}")
            return False
            
    async def get_all_employees(self) -> List[Dict]:
        """Get all employees from team sheet (backwards compatibility - uses cache)."""
        return await self.get_all_employees_cached()
            
    async def get_employees_without_reports(self, date: str = None) -> List[str]:
        """Get list of employee IDs who haven't submitted reports (backwards compatibility)."""
        employee_ids, _ = await self.get_employees_without_reports_batch(date)
        return employee_ids