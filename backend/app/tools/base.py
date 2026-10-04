import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class RiskLevel(Enum):
    LOW = "LOW"
    HIGH = "HIGH"


@dataclass
class ToolResult:
    success: bool
    data: Dict[str, Any]
    error: Optional[str]
    execution_time_ms: float


class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    @abstractmethod
    def risk_level(self) -> RiskLevel:
        pass

    @property
    def reversible(self) -> bool:
        return False

    @property
    def max_execution_seconds(self) -> int:
        return 30

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        pass

    @abstractmethod
    def validate_args(self, **kwargs) -> bool:
        pass

    def compute_payload_hash(self, **kwargs) -> str:
        sorted_json = json.dumps(kwargs, sort_keys=True)
        return hashlib.sha256(sorted_json.encode("utf-8")).hexdigest()

    def to_registry_entry(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "risk_level": self.risk_level.value,
            "reversible": self.reversible,
            "max_execution_seconds": self.max_execution_seconds,
        }


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [tool.to_registry_entry() for tool in self._tools.values()]

    def get_by_risk(self, level: RiskLevel) -> List[BaseTool]:
        return [tool for tool in self._tools.values() if tool.risk_level == level]


tool_registry = ToolRegistry()
