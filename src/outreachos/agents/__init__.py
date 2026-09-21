from .base import BaseAgent
from .hunter import HunterAgent
from .guardian import GuardianAgent
from .profiler import ProfilerAgent
from .copywriter import CopywriterAgent
from .sdr import SDRAgent
from .networker import NetworkerAgent
from .pipeline_agent import PipelineAgent
from .signal_scout import SignalScoutAgent
from .meeting_booker import MeetingBookerAgent
from .icp_refiner import ICPRefinerAgent
from .deliverability_ops import DeliverabilityOpsAgent
from .client_reporter import ClientReporterAgent

ALL_AGENTS = {
    HunterAgent.name: HunterAgent,
    GuardianAgent.name: GuardianAgent,
    ProfilerAgent.name: ProfilerAgent,
    CopywriterAgent.name: CopywriterAgent,
    SDRAgent.name: SDRAgent,
    NetworkerAgent.name: NetworkerAgent,
    PipelineAgent.name: PipelineAgent,
    SignalScoutAgent.name: SignalScoutAgent,
    MeetingBookerAgent.name: MeetingBookerAgent,
    ICPRefinerAgent.name: ICPRefinerAgent,
    DeliverabilityOpsAgent.name: DeliverabilityOpsAgent,
    ClientReporterAgent.name: ClientReporterAgent,
}

__all__ = ["BaseAgent", "HunterAgent", "GuardianAgent", "ProfilerAgent",
           "CopywriterAgent", "SDRAgent", "NetworkerAgent", "PipelineAgent",
           "SignalScoutAgent", "MeetingBookerAgent", "ICPRefinerAgent",
           "DeliverabilityOpsAgent", "ClientReporterAgent", "ALL_AGENTS"]
