# Telegram Bot Use Cases Documentation

## Overview
This document provides a comprehensive overview of all use cases for the BiaminoFeedbackTG Telegram bot, including user functionality, admin functionality, and automated triggers.

## 🧑‍💼 Employee (User) Use Cases

### Authentication & Basic Commands

#### UC-001: Initial Authentication
- **Trigger**: User sends `/start` command or any message to the bot
- **Flow**: 
  1. Bot automatically authenticates user by Telegram ID
  2. If user is found in employee database → Shows employee welcome message
  3. If user is admin → Shows admin welcome message
  4. If user not found → Shows error message asking to contact admin
- **Result**: User is authenticated and sees available commands

#### UC-002: Manual Report Creation
- **Trigger**: User sends `/report` command
- **Prerequisites**: User must be authenticated
- **Flow**:
  1. Bot retrieves tasks without reports for today
  2. If no tasks → Shows "General Report" option
  3. If tasks exist → Shows task selection menu with:
     - List of tasks with ID, description, and deadline
     - Option to create "General Report" (without specific task)
     - Cancel option
  4. User selects a task or general report
  5. Bot starts 3-step report collection process

#### UC-003: Multi-Step Report Collection
- **Prerequisites**: User has selected a task or general report
- **Flow**:
  1. **Step 1 - Feedback**: "How was working on this task? Was it interesting, what nuances did you encounter?"
  2. **Step 2 - Difficulties**: "Tell about difficulties. What went wrong, where help is needed?"
  3. **Step 3 - Daily Report**: "Describe what was done during the day. You can attach links to results."
  4. **Step 4 - Confirmation**: Shows summary of all inputs with options:
     - "Yes, send ✅" → Saves report to Google Sheets
     - "Fill again 🔄" → Restarts the process
- **Result**: Report is saved to Google Sheets with employee ID, task ID (if any), and all three fields

#### UC-004: Help and Information
- **Trigger**: User sends `/help` command
- **Result**: Shows available commands and bot information:
  - `/start` - Initial bot launch
  - `/report` - Fill report manually  
  - `/help` - Show help message
  - Information about automatic reminders at 21:00 MSK

#### UC-005: Logout
- **Trigger**: User sends `/logout` command
- **Result**: Clears user session, requires re-authentication


### Automated User Interactions

#### UC-007: Receive Automated Report Reminders
- **Trigger**: Scheduled at 21:00 MSK daily
- **Recipients**: All employees who haven't completed reports for ALL their tasks today
- **Message**: "Time for report! 📝 Use /report command to fill it."

#### UC-008: Receive Late Report Reminders  
- **Trigger**: Scheduled at 00:00 MSK (midnight) daily
- **Recipients**: Employees who didn't submit reports for previous day
- **Message**: "Seems you forgot to fill yesterday's report. Please don't forget! ⏰ Use /report command."

#### UC-009: Receive Task Notifications
- **Trigger**: Admin sends tasks or scheduled notifications
- **Format**: 
  ```
  📋 Hello, [Name]!
  
  You have active tasks:
  
  • Task_ID: Task description (deadline: DD.MM.YYYY)
  • Task_ID: Task description
  ```

#### UC-010: Receive Deadline Reminders
- **Trigger**: Automated hourly check for tasks with deadlines in next 12 hours
- **Format**:
  ```
  ⚠️ Deadline Reminder!
  
  Following tasks have deadline in 12 hours (DD.MM.YYYY):
  
  • Task_ID: Task description
  
  Don't forget to complete these tasks on time!
  ```

#### UC-011: Receive Broadcast Messages
- **Trigger**: Admin sends broadcast message
- **Content**: Any message type (text, photo, video, document, etc.) sent by admin

## 👑 Administrator Use Cases

### Admin Panel Access

#### UC-101: Admin Panel Access
- **Trigger**: Admin sends `/admin` command
- **Prerequisites**: User's Telegram ID must be in admin list
- **Result**: Shows admin panel with following options:
  - 📋 Send Tasks
  - ⏰ Report (to those who didn't submit)
  - 📢 Report (to everyone)  
  - 🔄 Send All Tasks to Everyone
  - 📡 Make Broadcast
  - ⏰ Deadline Reminders
  - 🔄 Notion Synchronization

### Task Management

#### UC-102: Selective Task Sending
- **Trigger**: Admin clicks "📋 Send Tasks" in admin panel
- **Flow**:
  1. Bot loads all employees who have active tasks
  2. Shows paginated employee selection (5 per page) with:
     - ✅/◻️ Employee Name (checkbox selection)
     - Pagination controls (⬅️ Back, ➡️ Next)
     - "✅ Select All" button
     - "📤 Send to Selected" button (only if selections made)
     - "❌ Cancel" button
  3. Admin selects employees and clicks "Send to Selected"
  4. Bot sends personalized task messages to selected employees
- **Result**: Shows summary with sent/failed counts

#### UC-103: Send All Tasks to Everyone
- **Trigger**: Admin clicks "🔄 Send All Tasks to Everyone"
- **Flow**: 
  1. Bot gets all employees with active tasks for today
  2. Sends task notifications to all of them
- **Result**: Shows summary with sent/failed counts

### Report Management & Statistics

#### UC-104: Remind Incomplete Reports
- **Trigger**: Admin clicks "⏰ Report (to those who didn't submit)"
- **Flow**:
  1. Bot checks who hasn't submitted complete reports for ALL their tasks today
  2. Sends reminder message to those employees
- **Message**: "Seems you forgot to fill today's report for some tasks. Please don't forget to fill reports for ALL incomplete tasks! ⏰"
- **Result**: Shows statistics with checked/sent/failed counts

#### UC-105: Remind All Employees
- **Trigger**: Admin clicks "📢 Report (to everyone)"
- **Flow**: Bot sends report reminder to ALL employees regardless of completion status
- **Message**: "Please don't forget to fill your daily report! 📝 Use /report command."
- **Result**: Shows sent count

#### UC-106: View Detailed Statistics
- **Trigger**: Admin sends `/stats` command
- **Result**: Shows comprehensive daily statistics:
  ```
  📊 Statistics for DD.MM.YYYY
  
  👥 Total employees: X
  ✅ Complete reports for all tasks: X  
  ❌ Incomplete reports: X
  📱 With TelegramID: X
  🚫 Without TelegramID: X
  
  Employees who didn't submit complete reports for all tasks:
  • Employee_ID
  • Employee_ID
  ...
  ```

### Communication & Broadcasting

#### UC-107: Universal Broadcast
- **Trigger**: Admin clicks "📡 Make Broadcast" in admin panel  
- **Flow**:
  1. Bot prompts: "Send message for broadcast to all users (text or media):"
  2. Admin sends ANY type of message (text, photo, video, document, audio, voice, animation, sticker, location, contact, poll)
  3. Bot forwards/sends the exact message to all employees
- **Result**: Shows broadcast completion statistics

### Deadline Management

#### UC-108: Manual Deadline Reminders
- **Trigger**: Admin clicks "⏰ Deadline Reminders" in admin panel
- **Flow**:
  1. Bot calculates deadline date (current time + 12 hours)
  2. Checks all employees for tasks with that deadline
  3. Sends deadline reminder messages
- **Result**: Shows detailed statistics:
  ```
  ⏰ Deadline Check Results:
  
  📊 Employees checked: X
  📋 With tasks on DD.MM.YYYY: X  
  ✅ Reminders sent: X
  ```

### System Management

#### UC-109: Notion Synchronization
- **Trigger**: Admin clicks "🔄 Notion Synchronization" in admin panel
- **Flow**: 
  1. Shows sync status message
  2. Indicates that sync runs automatically every 15 minutes
  3. Shows what data is synced from Notion to Google Sheets
- **Note**: Actual sync is handled by scheduled task, this is just informational

## 🤖 Automated System Use Cases

### Scheduled Triggers

#### UC-201: Daily Report Collection Trigger
- **Schedule**: Every day at 21:00 MSK
- **Action**: Sends report reminder to employees who haven't completed reports for ALL their tasks today
- **Implementation**: Uses `trigger_report_collection()` in scheduler

#### UC-202: Daily Late Report Reminders
- **Schedule**: Every day at 00:00 MSK (midnight)
- **Action**: Sends reminders to employees who didn't submit reports for previous day
- **Implementation**: Uses `send_reminders()` in scheduler

#### UC-203: Hourly Deadline Checks
- **Schedule**: Every hour at minute 0
- **Action**: 
  1. Calculates 12 hours from current time
  2. Finds all tasks with deadlines matching that time
  3. Sends deadline reminders to relevant employees
- **Implementation**: Uses `send_deadline_reminders()` in scheduler

#### UC-204: Notion Synchronization
- **Schedule**: Every 15 minutes
- **Action**: Syncs task data from Notion databases to Google Sheets
- **Implementation**: Uses `sync_notion_tasks()` in scheduler

### Data Management

#### UC-205: Google Sheets Integration
- **Purpose**: Central data storage for all reports, tasks, and employee information
- **Operations**:
  - Save daily reports (employee_id, task_id, feedback, difficulties, daily_report)
  - Retrieve employee data by Telegram ID
  - Get tasks without reports for specific dates
  - Get employees without complete reports
  - Batch operations for performance

#### UC-206: Caching System
- **Purpose**: Improve performance for frequently accessed data
- **Cached Data**: Employee lists, task lists
- **Refresh**: Automatic refresh for optimal performance

## 🔐 Authentication & Authorization

### User Authentication
- **Method**: Automatic authentication by Telegram ID
- **Admin Priority**: Admin users bypass employee database checks
- **Persistence**: Session maintained until `/logout` or system restart

### Admin Authorization  
- **Method**: Telegram ID must be in admin configuration list
- **Privileges**: Access to all admin commands and scheduling triggers
- **Bypass**: Admins don't need to be in employee database

## 📱 Message Types Supported

### User Reports
- Text messages (feedback, difficulties, daily reports)
- Media messages with captions
- Link attachments in daily reports

### Admin Broadcasts
- Text messages
- Photos with captions
- Videos  
- Documents
- Audio files
- Voice messages
- Video notes (circles)
- Animations/GIFs
- Stickers
- Location sharing
- Contact sharing
- Polls

## ⏰ Timing Summary

| Time (MSK) | Action | Target Audience |
|------------|--------|----------------|
| 21:00 daily | Report collection trigger | Employees without complete reports |
| 00:00 daily | Late report reminders | Employees who missed previous day |
| Every hour | Deadline reminders | Employees with tasks due in 12 hours |
| Every 15 min | Notion sync | System (background) |

## 🚨 Error Handling

- **Authentication failures**: Clear error messages to contact admin
- **Google Sheets errors**: Graceful fallback with error logging  
- **Message sending failures**: Rate limiting and retry logic
- **Validation errors**: User-friendly error messages with retry options
- **System errors**: Comprehensive logging for debugging

## 📊 Reporting & Analytics

- **Daily statistics**: Complete/incomplete reports, employee counts
- **Broadcast results**: Success/failure counts for mass messaging
- **Task distribution**: Tracking of task assignments and completion
- **Deadline tracking**: Monitoring of approaching deadlines
- **System performance**: Sync statistics and error rates