from pydantic import BaseModel, ConfigDict
from datetime import date, datetime
from typing import Optional, List
from .user import User


class TaskBase(BaseModel):
    activity_name: str
    status: str = "Not Started"
    planned_start: Optional[date] = None
    planned_finish: Optional[date] = None
    budgeted_cost: float = 0.0
    responsible_user_id: Optional[int] = None
    expected_output: Optional[str] = None
    depends_on: Optional[int] = None
    unit_of_measure: str = "units"
    total_quantity: float = 0.0
    completed_quantity: float = 0.0


class TaskCreate(TaskBase):
    project_id: int


class TaskUpdate(TaskBase):
    activity_name: Optional[str] = None
    project_id: Optional[int] = None


class TaskOutputBase(BaseModel):
    file_name: str
    file_path: str
    uploaded_by: Optional[int] = None
    doc_type: str = "Draft"


class TaskOutput(TaskOutputBase):
    output_id: int
    activity_id: int
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Task(TaskBase):
    activity_id: int
    project_id: int
    outputs: List[TaskOutput] = []
    responsible: Optional[User] = None

    model_config = ConfigDict(from_attributes=True)


class DailyProgressCreate(BaseModel):
    activity_id: int
    quantity: float
    progress_date: date
    notes: Optional[str] = None


class DailyProgress(BaseModel):
    progress_id: int
    activity_id: int
    quantity: float
    progress_date: date
    notes: Optional[str] = None
    recorded_by: Optional[int] = None
    recorded_at: datetime

    model_config = ConfigDict(from_attributes=True)
