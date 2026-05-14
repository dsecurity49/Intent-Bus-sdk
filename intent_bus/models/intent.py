'''Hardened, immutable protocol models for Intent Bus v2.0.'''
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, FrozenSet, Optional

from ..exceptions import IntentBusProtocolError
from ..constants import RESULT_JSON, RESULT_TEXT

@dataclass(slots=True, frozen=True)
class IntentBase:
    '''Base providing high-performance serialization and forward-compatibility.'''
    extra: Dict[str, Any] = field(default_factory=dict, kw_only=True)

    def to_dict(self) -> Dict[str, Any]:
        return self.extra.copy()

@dataclass(slots=True, frozen=True)
class ClaimedIntent(IntentBase):
    '''Immutable validated snapshot of a claimed intent.'''
    id: str
    goal: str
    payload: Any
    namespace: str = 'default'
    claim_attempts: int = 1
    priority: int = 100
    claim_timeout: int = 60
    target_worker: Optional[str] = None
    required_capability: Optional[str] = None

    _KNOWN: ClassVar[FrozenSet[str]] = frozenset({
        'id', 'goal', 'payload', 'namespace', 'claim_attempts', 
        'priority', 'claim_timeout', 'target_worker', 'required_capability'
    })

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ClaimedIntent':
        id_val, goal_val = data.get('id'), data.get('goal')
        if not isinstance(id_val, str) or not isinstance(goal_val, str):
            raise IntentBusProtocolError("Protocol Error: 'id' and 'goal' must be strings")

        try:
            known = {
                'id': id_val, 
                'goal': goal_val, 
                'payload': deepcopy(data.get('payload', {})),
                'namespace': str(data.get('namespace', 'default')),
                'claim_attempts': int(data.get('claim_attempts', 1)),
                'priority': int(data.get('priority', 100)),
                'claim_timeout': int(data.get('claim_timeout', 60)),
                'target_worker': data.get('target_worker'),
                'required_capability': data.get('required_capability')
            }
            extra = deepcopy({k: v for k, v in data.items() if k not in cls._KNOWN})
        except (TypeError, ValueError) as e:
            raise IntentBusProtocolError(f'Protocol Error: invalid numeric field: {e}') from e

        return cls(**known, extra=extra)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id, 'goal': self.goal, 'payload': self.payload, 'namespace': self.namespace,
            'claim_attempts': self.claim_attempts, 'priority': self.priority, 'claim_timeout': self.claim_timeout,
            'target_worker': self.target_worker, 'required_capability': self.required_capability,
            **self.extra.copy()
        }

@dataclass(slots=True, frozen=True)
class IntentStatus(IntentBase):
    '''Immutable lightweight status view.'''
    id: str
    status: str
    goal: str = ""  
    namespace: str = 'default'
    claim_attempts: int = 0
    run_at: Optional[float] = None
    error: Optional[str] = None

    _KNOWN: ClassVar[FrozenSet[str]] = frozenset({
        'id', 'status', 'goal', 'namespace', 'claim_attempts', 'run_at', 'error', 'last_error'
    })

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IntentStatus':
        id_val, status_val = data.get('id'), data.get('status')
        if not isinstance(id_val, str) or not isinstance(status_val, str):
            raise IntentBusProtocolError('Protocol Error: id and status must be strings')

        try:
            run_at_raw = data.get('run_at')
            error_val = data.get('error') or data.get('last_error') 

            known = {
                'id': id_val, 'status': status_val, 
                'goal': str(data.get('goal') or ''),
                'namespace': str(data.get('namespace', 'default')),
                'claim_attempts': int(data.get('claim_attempts', 0)),
                'run_at': float(run_at_raw) if run_at_raw is not None else None,
                'error': str(error_val) if error_val else None
            }
            extra = deepcopy({k: v for k, v in data.items() if k not in cls._KNOWN})
        except (TypeError, ValueError) as e:
            raise IntentBusProtocolError(f'Protocol Error: invalid numeric field: {e}') from e

        return cls(**known, extra=extra)

    def to_dict(self) -> Dict[str, Any]:
        base = {
            'id': self.id, 'status': self.status, 'goal': self.goal, 'namespace': self.namespace,
            'claim_attempts': self.claim_attempts, 'run_at': self.run_at, **self.extra.copy()
        }
        if self.error:
            base['error'] = self.error
        return base

@dataclass(slots=True, frozen=True)
class IntentResult(IntentStatus):
    '''Immutable detailed result snapshot.'''
    result: Any = None
    result_type: str = RESULT_JSON
    completed_at: Optional[float] = None

    _KNOWN: ClassVar[FrozenSet[str]] = frozenset(
        IntentStatus._KNOWN | {'result', 'result_type', 'completed_at'}
    )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IntentResult':
        id_val, status_val = data.get('id'), data.get('status')
        
        res_type_val = data.get('result_type')
        if res_type_val is None:
            res_type_val = RESULT_JSON
            
        if not isinstance(res_type_val, str):
            raise IntentBusProtocolError('Protocol Error: result_type must be a string')
        if res_type_val not in (RESULT_JSON, RESULT_TEXT):
            raise IntentBusProtocolError(f"Protocol Error: invalid incoming result_type: {res_type_val}")

        if not isinstance(id_val, str) or not isinstance(status_val, str):
            raise IntentBusProtocolError('Protocol Error: id and status must be strings')

        try:
            run_at_raw = data.get('run_at')
            comp_at_raw = data.get('completed_at')
            error_val = data.get('error') or data.get('last_error')

            known = {
                'id': id_val, 'status': status_val, 
                'goal': str(data.get('goal') or ''),
                'namespace': str(data.get('namespace', 'default')),
                'claim_attempts': int(data.get('claim_attempts', 0)),
                'run_at': float(run_at_raw) if run_at_raw is not None else None,
                'error': str(error_val) if error_val else None,
                'result': deepcopy(data.get('result')),
                'result_type': res_type_val,
                'completed_at': float(comp_at_raw) if comp_at_raw is not None else None
            }
            extra = deepcopy({k: v for k, v in data.items() if k not in cls._KNOWN})
        except (TypeError, ValueError) as e:
            raise IntentBusProtocolError(f'Protocol Error: invalid numeric field: {e}') from e

        return cls(**known, extra=extra)

    def to_dict(self) -> Dict[str, Any]:
        base = {
            'id': self.id, 'status': self.status, 'goal': self.goal, 'namespace': self.namespace,
            'claim_attempts': self.claim_attempts, 'run_at': self.run_at, 'result': self.result,
            'result_type': self.result_type, 'completed_at': self.completed_at, **self.extra.copy()
        }
        if self.error:
            base['error'] = self.error
        return base
