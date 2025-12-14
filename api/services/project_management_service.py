"""
Project Management Integration Service for Hampstead Renovations Voice AI Agent

Integrates with project management tools:
- Monday.com integration
- Asana integration
- Project timeline updates
- Task creation from conversations
"""

import asyncio
import logging
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
import httpx
from config import settings

logger = logging.getLogger(__name__)


class ProjectStatus(Enum):
    """Project status stages"""
    LEAD = "lead"
    CONSULTATION_BOOKED = "consultation_booked"
    QUOTED = "quoted"
    ACCEPTED = "accepted"
    PLANNING = "planning"
    IN_PROGRESS = "in_progress"
    SNAGGING = "snagging"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """Task priority levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class PMPlatform(Enum):
    """Supported project management platforms"""
    MONDAY = "monday"
    ASANA = "asana"
    TRELLO = "trello"


@dataclass
class ProjectTask:
    """A task within a project"""
    id: str
    title: str
    description: str
    status: str
    priority: TaskPriority
    assignee: Optional[str] = None
    due_date: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    tags: list[str] = field(default_factory=list)


@dataclass
class Project:
    """A renovation project"""
    id: str
    name: str
    client_name: str
    client_email: Optional[str]
    client_phone: Optional[str]
    status: ProjectStatus
    service_type: str
    address: Optional[str] = None
    estimated_value: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    tasks: list[ProjectTask] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)


class MondayClient:
    """Monday.com API client"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_url = "https://api.monday.com/v2"
        self.headers = {
            "Authorization": api_key,
            "Content-Type": "application/json"
        }
        
    async def execute_query(self, query: str, variables: Optional[dict] = None) -> dict:
        """Execute a GraphQL query"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.api_url,
                headers=self.headers,
                json={"query": query, "variables": variables or {}},
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
            
    async def get_boards(self) -> list[dict]:
        """Get all boards"""
        query = """
        query {
            boards {
                id
                name
                state
            }
        }
        """
        result = await self.execute_query(query)
        return result.get("data", {}).get("boards", [])
        
    async def create_item(
        self,
        board_id: str,
        item_name: str,
        column_values: Optional[dict] = None
    ) -> dict:
        """Create a new item (project/lead)"""
        column_values_json = json.dumps(column_values) if column_values else "{}"
        
        query = f"""
        mutation {{
            create_item (
                board_id: {board_id},
                item_name: "{item_name}",
                column_values: "{column_values_json.replace('"', '\\"')}"
            ) {{
                id
                name
            }}
        }}
        """
        result = await self.execute_query(query)
        return result.get("data", {}).get("create_item", {})
        
    async def update_item(
        self,
        board_id: str,
        item_id: str,
        column_values: dict
    ) -> dict:
        """Update an item's column values"""
        column_values_json = json.dumps(column_values)
        
        query = f"""
        mutation {{
            change_multiple_column_values (
                board_id: {board_id},
                item_id: {item_id},
                column_values: "{column_values_json.replace('"', '\\"')}"
            ) {{
                id
                name
            }}
        }}
        """
        result = await self.execute_query(query)
        return result.get("data", {}).get("change_multiple_column_values", {})
        
    async def add_update(self, item_id: str, body: str) -> dict:
        """Add an update/note to an item"""
        query = f"""
        mutation {{
            create_update (
                item_id: {item_id},
                body: "{body.replace('"', '\\"')}"
            ) {{
                id
            }}
        }}
        """
        result = await self.execute_query(query)
        return result.get("data", {}).get("create_update", {})


class AsanaClient:
    """Asana API client"""
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.api_url = "https://app.asana.com/api/1.0"
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict] = None
    ) -> dict:
        """Make an API request"""
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                f"{self.api_url}{endpoint}",
                headers=self.headers,
                json={"data": data} if data else None,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json().get("data", {})
            
    async def get_workspaces(self) -> list[dict]:
        """Get all workspaces"""
        return await self._request("GET", "/workspaces")
        
    async def get_projects(self, workspace_id: str) -> list[dict]:
        """Get all projects in a workspace"""
        return await self._request("GET", f"/workspaces/{workspace_id}/projects")
        
    async def create_task(
        self,
        project_id: str,
        name: str,
        notes: Optional[str] = None,
        due_on: Optional[str] = None,
        assignee: Optional[str] = None
    ) -> dict:
        """Create a new task"""
        data = {
            "name": name,
            "projects": [project_id]
        }
        if notes:
            data["notes"] = notes
        if due_on:
            data["due_on"] = due_on
        if assignee:
            data["assignee"] = assignee
            
        return await self._request("POST", "/tasks", data)
        
    async def update_task(self, task_id: str, data: dict) -> dict:
        """Update a task"""
        return await self._request("PUT", f"/tasks/{task_id}", data)
        
    async def add_comment(self, task_id: str, text: str) -> dict:
        """Add a comment to a task"""
        return await self._request("POST", f"/tasks/{task_id}/stories", {"text": text})


class ProjectManagementService:
    """
    Project management integration service
    
    Provides:
    - Monday.com integration
    - Asana integration
    - Unified project/task management
    - Automatic updates from conversations
    """
    
    # Status mapping for Monday.com
    MONDAY_STATUS_MAP = {
        ProjectStatus.LEAD: {"label": "Lead"},
        ProjectStatus.CONSULTATION_BOOKED: {"label": "Consultation Booked"},
        ProjectStatus.QUOTED: {"label": "Quoted"},
        ProjectStatus.ACCEPTED: {"label": "Accepted"},
        ProjectStatus.PLANNING: {"label": "Planning"},
        ProjectStatus.IN_PROGRESS: {"label": "In Progress"},
        ProjectStatus.SNAGGING: {"label": "Snagging"},
        ProjectStatus.COMPLETED: {"label": "Completed"},
        ProjectStatus.ON_HOLD: {"label": "On Hold"},
        ProjectStatus.CANCELLED: {"label": "Cancelled"}
    }
    
    def __init__(self):
        self.monday_client: Optional[MondayClient] = None
        self.asana_client: Optional[AsanaClient] = None
        self._active_platform: Optional[PMPlatform] = None
        self._config: dict = {}
        
    async def initialize(
        self,
        platform: PMPlatform,
        api_key: str,
        board_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        project_id: Optional[str] = None
    ):
        """
        Initialize the project management integration
        
        Args:
            platform: Which platform to use
            api_key: API key or access token
            board_id: Monday.com board ID
            workspace_id: Asana workspace ID
            project_id: Asana project ID
        """
        self._active_platform = platform
        
        if platform == PMPlatform.MONDAY:
            self.monday_client = MondayClient(api_key)
            self._config = {"board_id": board_id}
            logger.info(f"Initialized Monday.com integration with board {board_id}")
            
        elif platform == PMPlatform.ASANA:
            self.asana_client = AsanaClient(api_key)
            self._config = {
                "workspace_id": workspace_id,
                "project_id": project_id
            }
            logger.info(f"Initialized Asana integration with project {project_id}")
            
    async def create_project_from_lead(
        self,
        client_name: str,
        client_phone: Optional[str] = None,
        client_email: Optional[str] = None,
        service_type: str = "General Inquiry",
        notes: Optional[str] = None,
        source: str = "Voice AI"
    ) -> Optional[str]:
        """
        Create a new project/lead from conversation
        
        Args:
            client_name: Name of the client
            client_phone: Phone number
            client_email: Email address
            service_type: Type of service interested in
            notes: Initial notes from conversation
            source: Lead source
            
        Returns:
            Project/item ID if successful
        """
        if self._active_platform == PMPlatform.MONDAY and self.monday_client:
            return await self._create_monday_item(
                client_name, client_phone, client_email,
                service_type, notes, source
            )
        elif self._active_platform == PMPlatform.ASANA and self.asana_client:
            return await self._create_asana_task(
                client_name, client_phone, client_email,
                service_type, notes, source
            )
        else:
            logger.warning("No project management platform configured")
            return None
            
    async def _create_monday_item(
        self,
        client_name: str,
        client_phone: Optional[str],
        client_email: Optional[str],
        service_type: str,
        notes: Optional[str],
        source: str
    ) -> Optional[str]:
        """Create a Monday.com item"""
        if not self.monday_client or not self._config.get("board_id"):
            return None
            
        try:
            # Column values - adjust based on your Monday.com board structure
            column_values = {
                "status": {"label": "Lead"},
                "text": service_type,  # Service type column
                "text4": source,  # Source column
            }
            
            if client_phone:
                column_values["phone"] = {"phone": client_phone, "countryShortName": "GB"}
            if client_email:
                column_values["email"] = {"email": client_email, "text": client_email}
                
            result = await self.monday_client.create_item(
                self._config["board_id"],
                client_name,
                column_values
            )
            
            item_id = result.get("id")
            
            # Add notes as an update
            if notes and item_id:
                await self.monday_client.add_update(
                    item_id,
                    f"📞 Voice AI Conversation Notes:\n\n{notes}"
                )
                
            logger.info(f"Created Monday.com item {item_id} for {client_name}")
            return item_id
            
        except Exception as e:
            logger.error(f"Failed to create Monday.com item: {e}")
            return None
            
    async def _create_asana_task(
        self,
        client_name: str,
        client_phone: Optional[str],
        client_email: Optional[str],
        service_type: str,
        notes: Optional[str],
        source: str
    ) -> Optional[str]:
        """Create an Asana task"""
        if not self.asana_client or not self._config.get("project_id"):
            return None
            
        try:
            # Build task notes
            task_notes = f"""New Lead from {source}

Client: {client_name}
Phone: {client_phone or 'Not provided'}
Email: {client_email or 'Not provided'}
Service Interest: {service_type}

---
Conversation Notes:
{notes or 'No notes'}"""

            result = await self.asana_client.create_task(
                self._config["project_id"],
                f"Lead: {client_name} - {service_type}",
                notes=task_notes
            )
            
            task_id = result.get("gid")
            logger.info(f"Created Asana task {task_id} for {client_name}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to create Asana task: {e}")
            return None
            
    async def update_project_status(
        self,
        project_id: str,
        new_status: ProjectStatus,
        notes: Optional[str] = None
    ) -> bool:
        """
        Update project status
        
        Args:
            project_id: ID of the project/item
            new_status: New status
            notes: Optional notes about the update
            
        Returns:
            True if successful
        """
        if self._active_platform == PMPlatform.MONDAY and self.monday_client:
            try:
                column_values = {"status": self.MONDAY_STATUS_MAP.get(new_status, {"label": "Lead"})}
                
                await self.monday_client.update_item(
                    self._config["board_id"],
                    project_id,
                    column_values
                )
                
                if notes:
                    await self.monday_client.add_update(
                        project_id,
                        f"Status updated to {new_status.value}:\n{notes}"
                    )
                    
                logger.info(f"Updated Monday.com item {project_id} to {new_status.value}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to update Monday.com item: {e}")
                return False
                
        elif self._active_platform == PMPlatform.ASANA and self.asana_client:
            try:
                # Asana uses custom fields or sections for status
                # This would need to be customized based on your Asana setup
                if notes:
                    await self.asana_client.add_comment(
                        project_id,
                        f"Status update: {new_status.value}\n\n{notes}"
                    )
                    
                logger.info(f"Added status update to Asana task {project_id}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to update Asana task: {e}")
                return False
                
        return False
        
    async def add_conversation_note(
        self,
        project_id: str,
        note: str,
        author: str = "Voice AI"
    ) -> bool:
        """
        Add a note from conversation to a project
        
        Args:
            project_id: ID of the project/item
            note: Note content
            author: Who added the note
            
        Returns:
            True if successful
        """
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        formatted_note = f"📝 {author} ({timestamp}):\n\n{note}"
        
        if self._active_platform == PMPlatform.MONDAY and self.monday_client:
            try:
                await self.monday_client.add_update(project_id, formatted_note)
                return True
            except Exception as e:
                logger.error(f"Failed to add Monday.com note: {e}")
                return False
                
        elif self._active_platform == PMPlatform.ASANA and self.asana_client:
            try:
                await self.asana_client.add_comment(project_id, formatted_note)
                return True
            except Exception as e:
                logger.error(f"Failed to add Asana comment: {e}")
                return False
                
        return False
        
    async def create_task_from_conversation(
        self,
        project_id: str,
        task_title: str,
        task_description: str,
        due_date: Optional[datetime] = None,
        priority: TaskPriority = TaskPriority.MEDIUM
    ) -> Optional[str]:
        """
        Create a task from conversation context
        
        Args:
            project_id: Parent project/item ID
            task_title: Title of the task
            task_description: Description
            due_date: When it's due
            priority: Priority level
            
        Returns:
            Task ID if successful
        """
        if self._active_platform == PMPlatform.MONDAY and self.monday_client:
            # Monday.com uses subitems for tasks
            note = f"🎯 Task Created: {task_title}\n\nPriority: {priority.value}\nDue: {due_date.strftime('%Y-%m-%d') if due_date else 'Not set'}\n\n{task_description}"
            await self.monday_client.add_update(project_id, note)
            return "task_noted"  # Monday.com subitems require different API
            
        elif self._active_platform == PMPlatform.ASANA and self.asana_client:
            try:
                result = await self.asana_client.create_task(
                    self._config["project_id"],
                    task_title,
                    notes=task_description,
                    due_on=due_date.strftime("%Y-%m-%d") if due_date else None
                )
                return result.get("gid")
            except Exception as e:
                logger.error(f"Failed to create Asana task: {e}")
                return None
                
        return None
        
    async def get_project_summary(self, project_id: str) -> Optional[dict]:
        """Get a summary of a project for conversation context"""
        # This would fetch project details from the PM platform
        # Implementation depends on the specific platform and board/project structure
        return {
            "id": project_id,
            "status": "unknown",
            "message": "Project summary requires platform-specific implementation"
        }
        
    async def schedule_followup(
        self,
        project_id: str,
        followup_date: datetime,
        reason: str
    ) -> bool:
        """Schedule a follow-up task"""
        return await self.create_task_from_conversation(
            project_id,
            f"Follow-up: {reason}",
            f"Scheduled follow-up from Voice AI conversation.\n\nReason: {reason}",
            due_date=followup_date,
            priority=TaskPriority.MEDIUM
        ) is not None


# Module-level instance
project_service = ProjectManagementService()
