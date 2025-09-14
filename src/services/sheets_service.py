"""Google Sheets service module."""
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
from loguru import logger
import gspread
from google.oauth2.service_account import Credentials


class GoogleSheetsService:
    """Service for working with Google Sheets."""
    
    def __init__(self, service_account_file: str, spreadsheet_id: str):
        self.service_account_file = service_account_file
        self.spreadsheet_id = spreadsheet_id
        self.gc = None
        self.sh = None
        
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
            
    async def verify_employee_password(self, last_name: str, first_name: str, password: str) -> Optional[Dict]:
        """Verify employee credentials and return employee data."""
        employee_data = await self.get_employee_data(last_name, first_name)
        
        if employee_data:
            stored_password = employee_data.get("Пароль")
            logger.info(f"Stored password: {stored_password} (type: {type(stored_password)})")
            logger.info(f"Input password: {password} (type: {type(password)})")
            
            # Convert both to strings for comparison to handle int/str mismatch
            if str(stored_password) == str(password):
                logger.info("Password verification successful")
                return employee_data
            else:
                logger.warning(f"Password mismatch: stored='{stored_password}', input='{password}'")
        else:
            logger.warning("Employee data not found for password verification")
        
        return None
        
    async def get_employee_tasks(self, employee_id: str, date: str = None) -> Optional[str]:
        """Get tasks for employee for specific date."""
        if date is None:
            date = datetime.now().strftime("%d.%m.%Y")
            
        try:
            employee_sheet = self.sh.worksheet(employee_id)
            records = employee_sheet.get_all_records()
            
            # Find record for today's date
            for record in records:
                if record.get("Дата") == date:
                    return record.get("Задачи", "")
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
            
            # Check if report for today already exists
            records = employee_sheet.get_all_records()
            row_to_update = None
            
            for i, record in enumerate(records):
                if record.get("Дата") == today:
                    row_to_update = i + 2  # +2 because records are 0-indexed and sheet is 1-indexed + header
                    break
                    
            if row_to_update:
                # Update existing row
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
            records = employee_sheet.get_all_records()
            
            for record in records:
                if record.get("Дата") == date:
                    # Check all required columns are filled
                    feedback = record.get("Фидбек по задачам", "").strip()
                    difficulties = record.get("Сложности по задачам", "").strip()
                    daily_report = record.get("Отчет за день", "").strip()
                    
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
        """Get all employees from 'Команда' sheet."""
        try:
            team_sheet = self.sh.worksheet("Команда")
            records = team_sheet.get_all_records()
            logger.info(f"Retrieved {len(records)} employees from Google Sheets")
            
            # Debug: show first employee to verify column names
            if records:
                logger.debug(f"First employee data: {records[0]}")
                logger.debug(f"Available columns: {list(records[0].keys())}")
            
            return records
            
        except Exception as e:
            logger.error(f"Error getting all employees: {e}")
            return []
            
    async def get_employees_without_reports(self, date: str = None) -> List[str]:
        """Get list of employee IDs who haven't submitted reports."""
        if date is None:
            date = datetime.now().strftime("%d.%m.%Y")
            
        employees = await self.get_all_employees()
        employees_without_reports = []
        
        for employee in employees:
            employee_id = employee.get("ID", "")
            if employee_id:
                has_report = await self.check_report_submitted(employee_id, date)
                if not has_report:
                    employees_without_reports.append(employee_id)
                    
        return employees_without_reports
        
    async def update_employee_tasks(self, employee_id: str, tasks: str, date: str = None) -> bool:
        """Update tasks for employee for specific date."""
        if date is None:
            date = datetime.now().strftime("%d.%m.%Y")
            
        try:
            employee_sheet = self.sh.worksheet(employee_id)
            records = employee_sheet.get_all_records()
            
            # Find record for the date
            row_to_update = None
            for i, record in enumerate(records):
                if record.get("Дата") == date:
                    row_to_update = i + 2  # +2 because records are 0-indexed and sheet is 1-indexed + header
                    break
                    
            if row_to_update:
                # Update existing row
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