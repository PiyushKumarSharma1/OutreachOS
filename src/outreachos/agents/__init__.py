from .base import BaseAgent
from .hunter import HunterAgent
from .guardian import GuardianAgent
from .profiler import ProfilerAgent
from .copywriter import CopywriterAgent
from .sdr import SDRAgent
from .networker import NetworkerAgent
from .pipeline_agent import PipelineAgent

ALL_AGENTS = {
    HunterAgent.name: HunterAgent,
    GuardianAgent.name: GuardianAgent,
    ProfilerAgent.name: ProfilerAgent,
    CopywriterAgent.name: CopywriterAgent,
    SDRAgent.name: SDRAgent,
    NetworkerAgent.name: NetworkerAgent,
    PipelineAgent.name: PipelineAgent,
}

__all__ = ["BaseAgent", "HunterAgent", "GuardianAgent", "ProfilerAgent",
           "CopywriterAgent", "SDRAgent", "NetworkerAgent", "PipelineAgent", "ALL_AGENTS"]
