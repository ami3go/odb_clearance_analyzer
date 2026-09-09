"""ODB++ net-to-net clearance analyzer."""

from .analyzer import ClearanceAnalyzer
from .run_output import enable_timestamped_report_runs
from .gui_zone1_default import install_zone1_default_gui_patch
from .models import AnalysisCancelled, AnalysisConfig, AnalysisResult, EffectiveAirGapRecord, FeatureAttributeRecord, MeasurementRecord

__all__ = [
    "AnalysisCancelled",
    "AnalysisConfig",
    "AnalysisResult",
    "ClearanceAnalyzer",
    "EffectiveAirGapRecord",
    "FeatureAttributeRecord",
    "MeasurementRecord",
]

enable_timestamped_report_runs(ClearanceAnalyzer)
install_zone1_default_gui_patch()

__version__ = "0.4.43"
