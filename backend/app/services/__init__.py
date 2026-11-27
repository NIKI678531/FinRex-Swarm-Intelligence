"""
业务服务模块

轻量场景（如只跑执行层）可能缺少 zep / camel 等可选依赖，这里采用建议式导入。
"""

import logging as _logging

_logger = _logging.getLogger('finrex.services.bootstrap')


def _try_import(callable_):
    try:
        callable_()
    except Exception as exc:  # pragma: no cover - depends on optional deps
        _logger.warning('跳过可选服务导入：%s', exc)


def _import_core():
    global OntologyGenerator, GraphBuilderService, TextProcessor
    from .ontology_generator import OntologyGenerator as _O
    from .graph_builder import GraphBuilderService as _G
    from .text_processor import TextProcessor as _T
    OntologyGenerator, GraphBuilderService, TextProcessor = _O, _G, _T


def _import_zep():
    global ZepEntityReader, EntityNode, FilteredEntities
    global ZepGraphMemoryUpdater, ZepGraphMemoryManager, AgentActivity
    from .zep_entity_reader import ZepEntityReader as _Z, EntityNode as _E, FilteredEntities as _F
    from .zep_graph_memory_updater import ZepGraphMemoryUpdater as _U, ZepGraphMemoryManager as _M, AgentActivity as _A
    ZepEntityReader, EntityNode, FilteredEntities = _Z, _E, _F
    ZepGraphMemoryUpdater, ZepGraphMemoryManager, AgentActivity = _U, _M, _A


def _import_oasis():
    global OasisProfileGenerator, OasisAgentProfile
    global SimulationManager, SimulationState, SimulationStatus
    global SimulationConfigGenerator, SimulationParameters
    global AgentActivityConfig, TimeSimulationConfig, EventConfig, PlatformConfig
    global SimulationRunner, SimulationRunState, RunnerStatus, AgentAction, RoundSummary
    global SimulationIPCClient, SimulationIPCServer, IPCCommand, IPCResponse, CommandType, CommandStatus
    from .oasis_profile_generator import OasisProfileGenerator, OasisAgentProfile
    from .simulation_manager import SimulationManager, SimulationState, SimulationStatus
    from .simulation_config_generator import (
        SimulationConfigGenerator,
        SimulationParameters,
        AgentActivityConfig,
        TimeSimulationConfig,
        EventConfig,
        PlatformConfig,
    )
    from .simulation_runner import (
        SimulationRunner,
        SimulationRunState,
        RunnerStatus,
        AgentAction,
        RoundSummary,
    )
    from .simulation_ipc import (
        SimulationIPCClient,
        SimulationIPCServer,
        IPCCommand,
        IPCResponse,
        CommandType,
        CommandStatus,
    )


_try_import(_import_core)
_try_import(_import_zep)
_try_import(_import_oasis)

__all__ = [
    'OntologyGenerator', 
    'GraphBuilderService', 
    'TextProcessor',
    'ZepEntityReader',
    'EntityNode',
    'FilteredEntities',
    'OasisProfileGenerator',
    'OasisAgentProfile',
    'SimulationManager',
    'SimulationState',
    'SimulationStatus',
    'SimulationConfigGenerator',
    'SimulationParameters',
    'AgentActivityConfig',
    'TimeSimulationConfig',
    'EventConfig',
    'PlatformConfig',
    'SimulationRunner',
    'SimulationRunState',
    'RunnerStatus',
    'AgentAction',
    'RoundSummary',
    'ZepGraphMemoryUpdater',
    'ZepGraphMemoryManager',
    'AgentActivity',
    'SimulationIPCClient',
    'SimulationIPCServer',
    'IPCCommand',
    'IPCResponse',
    'CommandType',
    'CommandStatus',
]

