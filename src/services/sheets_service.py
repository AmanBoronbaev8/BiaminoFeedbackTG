"""Google Sheets service module."""
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Set
from loguru import logger
import gspread
from google.oauth2.service_account import Credentials

from ..utils.telegram_utils import parse_telegram_ids


class GoogleSheetsService:
    """Service for working with Google Sheets."""
    
    def __init__(self, service_account_file: str, spreadsheet_id: str):
        self.service_account_file = service_account_file
        self.spreadsheet_id = spreadsheet_id
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
        """Get employee data from 'Команда' sheet."""
        try:
            logger.debug(f"Getting employee data for: {last_name} {first_name}")
            team_sheet = self.sh.worksheet("Команда")
            records = team_sheet.get_all_records()
            logger.debug(f"Found {len(records)} records in team sheet")
            
            for i, record in enumerate(records):
                logger.debug(f"Record {i}: {record}")
                if (record.get("Фамилия", "").strip().lower() == last_name.strip().lower() and 
                    record.get("Имя", "").strip().lower() == first_name.strip().lower()):
                    logger.info(f"Found employee: {record}")
                    return record
            
            logger.warning(f"Employee not found: {last_name} {first_name}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting employee data: {e}")
            return None
            
    async def get_employee_by_telegram_id(self, telegram_id: int) -> Optional[Dict]:
        """Get employee data by TelegramID from 'Команда' sheet."""
        try:
            logger.debug(f"Getting employee data for TelegramID: {telegram_id}")
            team_sheet = self.sh.worksheet("Команда")
            records = team_sheet.get_all_records()
            logger.debug(f"Found {len(records)} records in team sheet")
            
            for i, record in enumerate(records):
                stored_telegram_id = record.get("TelegramID", "")
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
            team_sheet = self.sh.worksheet("Команда")
            records = team_sheet.get_all_records()
            
            self._employees_cache = records
            self._cache_timestamp = datetime.now().timestamp()
            
            logger.info(f"Employee cache refreshed with {len(records)} records")
            return records
            
        except Exception as e:
            logger.error(f"Error refreshing employee cache: {e}")
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
            employee_id = employee.get("ID", "")
            if not employee_id:
                continue
                
            tasks = await self.get_employee_tasks(employee_id, date)
            if tasks and tasks.strip():
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
            employee_id = employee.get("ID", "")
            if not employee_id:
                continue
                
            has_report = await self.check_report_submitted(employee_id, date)
            if not has_report:
                employees_without_reports.append(employee_id)
                # Only include employees with valid TelegramID for messaging
                telegram_ids = parse_telegram_ids(employee.get("TelegramID"))
                if telegram_ids:
                    employees_with_telegram.append(employee)
                    
        return employees_without_reports, employees_with_telegram
            

    async def get_employee_tasks(self, employee_id: str, date: str = None) -> Optional[str]:
        """Get tasks for employee for specific date."""
        if date is None:
            date = datetime.now().strftime("%d.%m.%Y")
            
        try:
            employee_sheet = self.sh.worksheet(employee_id)
            
            # Get raw values to avoid duplicate header issues
            all_values = employee_sheet.get_all_values()
            
            if not all_values or len(all_values) < 2:  # No data or only header
                return ""
                
            # Get header row to find column indices
            header_row = all_values[0] if all_values else []
            
            # Find column indices
            date_col = None
            tasks_col = None
            
            for i, header in enumerate(header_row):
                if header == "Дата":
                    date_col = i
                elif header == "Задачи":
                    tasks_col = i
            
            # Search for the date in data rows
            for row in all_values[1:]:  # Skip header row
                if len(row) > date_col and date_col is not None and row[date_col] == date:
                    return row[tasks_col] if tasks_col is not None and len(row) > tasks_col else ""
            
            return ""
            
        except Exception as e:
            logger.error(f"Error getting tasks for {employee_id}: {e}")
            return None
            
    async def save_daily_report(self, employee_id: str, feedback: str, difficulties: str, daily_report: str) -> bool:
        """Save daily report to employee's sheet."""
        try:
            today = datetime.now().strftime("%d.%m.%Y")
            
            # Get or create employee sheet
            try:
                employee_sheet = self.sh.worksheet(employee_id)
            except:
                # Create new sheet if doesn't exist
                employee_sheet = self.sh.add_worksheet(
                    title=employee_id, 
                    rows="1000", 
                    cols="5"
                )
                # Add headers with exact column names
                employee_sheet.update('A1:E1', [["Дата", "Задачи", "Фидбек по задачам", "Сложности по задачам", "Отчет за день"]])
            
            # Get raw values to avoid duplicate header issues
            all_values = employee_sheet.get_all_values()
            
            if not all_values:
                # No data, add headers and the report
                employee_sheet.update('A1:E1', [["Дата", "Задачи", "Фидбек по задачам", "Сложности по задачам", "Отчет за день"]])
                new_row = [today, "", feedback, difficulties, daily_report]
                employee_sheet.append_row(new_row)
                logger.info(f"Saved daily report for {employee_id} on {today}")
                return True
                
            # Find column indices
            header_row = all_values[0] if all_values else []
            date_col = None
            
            for i, header in enumerate(header_row):
                if header == "Дата":
                    date_col = i
                    break
            
            # Find existing row for today
            row_to_update = None
            for i, row in enumerate(all_values[1:], start=2):  # Start from row 2 (1-indexed)
                if len(row) > date_col and date_col is not None and row[date_col] == today:
                    row_to_update = i
                    break
                    
            if row_to_update:
                # Update existing row (columns C, D, E for feedback, difficulties, daily_report)
                employee_sheet.update(f'C{row_to_update}:E{row_to_update}', [[feedback, difficulties, daily_report]])
            else:
                # Add new row
                new_row = [today, "", feedback, difficulties, daily_report]
                employee_sheet.append_row(new_row)
                
            logger.info(f"Saved daily report for {employee_id} on {today}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving daily report for {employee_id}: {e}")
            return False
            
    async def check_report_submitted(self, employee_id: str, date: str = None) -> bool:
        """Check if employee has submitted report for the date.
        
        Checks that all required columns are filled:
        - 'Фидбек по задачам'
        - 'Сложности по задачам'
        - 'Отчет за день'
        """
        if date is None:
            date = datetime.now().strftime("%d.%m.%Y")
            
        try:
            employee_sheet = self.sh.worksheet(employee_id)
            
            # Get raw values to avoid duplicate header issues
            all_values = employee_sheet.get_all_values()
            
            if not all_values or len(all_values) < 2:  # No data or only header
                return False
                
            # Get header row to find column indices
            header_row = all_values[0] if all_values else []
            
            # Find column indices for required fields
            date_col = None
            feedback_col = None
            difficulties_col = None
            daily_report_col = None
            
            for i, header in enumerate(header_row):
                if header == "Дата":
                    date_col = i
                elif header == "Фидбек по задачам":
                    feedback_col = i
                elif header == "Сложности по задачам":
                    difficulties_col = i
                elif header == "Отчет за день":
                    daily_report_col = i
            
            # Check if we found all required columns
            if None in [date_col, feedback_col, difficulties_col, daily_report_col]:
                logger.warning(f"Missing required columns in sheet {employee_id}")
                return False
            
            # Search for the date in data rows
            for row in all_values[1:]:  # Skip header row
                if len(row) > date_col and row[date_col] == date:
                    # Check if all required columns are filled
                    feedback = row[feedback_col].strip() if len(row) > feedback_col else ""
                    difficulties = row[difficulties_col].strip() if len(row) > difficulties_col else ""
                    daily_report = row[daily_report_col].strip() if len(row) > daily_report_col else ""
                    
                    # Return True only if ALL columns are filled
                    if feedback and difficulties and daily_report:
                        return True
                    else:
                        logger.info(f"Employee {employee_id} has incomplete report for {date}: "
                                   f"feedback={bool(feedback)}, difficulties={bool(difficulties)}, "
                                   f"daily_report={bool(daily_report)}")
                        return False
            
            # No record found for this date
            return False
            
        except Exception as e:
            logger.error(f"Error checking report for {employee_id}: {e}")
            return False
            
    async def get_all_employees(self) -> List[Dict]:
        """Get all employees from 'Команда' sheet (backwards compatibility - uses cache)."""
        return await self.get_all_employees_cached()
            
    async def get_employees_without_reports(self, date: str = None) -> List[str]:
        """Get list of employee IDs who haven't submitted reports (backwards compatibility)."""
        employee_ids, _ = await self.get_employees_without_reports_batch(date)
        return employee_ids
        
    async def update_employee_tasks(self, employee_id: str, tasks: str, date: str = None) -> bool:
        """Update tasks for employee for specific date."""
        if date is None:
            date = datetime.now().strftime("%d.%m.%Y")
            
        try:
            employee_sheet = self.sh.worksheet(employee_id)
            
            # Get raw values to avoid duplicate header issues
            all_values = employee_sheet.get_all_values()
            
            if not all_values:
                # No data, add headers and the task
                employee_sheet.update('A1:E1', [["Дата", "Задачи", "Фидбек по задачам", "Сложности по задачам", "Отчет за день"]])
                new_row = [date, tasks, "", "", ""]
                employee_sheet.append_row(new_row)
                logger.info(f"Updated tasks for {employee_id} on {date}")
                return True
                
            # Find column indices
            header_row = all_values[0] if all_values else []
            date_col = None
            
            for i, header in enumerate(header_row):
                if header == "Дата":
                    date_col = i
                    break
            
            # Find existing row for the date
            row_to_update = None
            for i, row in enumerate(all_values[1:], start=2):  # Start from row 2 (1-indexed)
                if len(row) > date_col and date_col is not None and row[date_col] == date:
                    row_to_update = i
                    break
                    
            if row_to_update:
                # Update existing row (column B for tasks)
                employee_sheet.update(f'B{row_to_update}', tasks)
            else:
                # Add new row
                new_row = [date, tasks, "", "", ""]
                employee_sheet.append_row(new_row)
                
            logger.info(f"Updated tasks for {employee_id} on {date}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating tasks for {employee_id}: {e}")
            return False