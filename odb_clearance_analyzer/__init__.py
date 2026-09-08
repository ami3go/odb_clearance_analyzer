"""ODB++ net-to-net clearance analyzer."""

from .analyzer import ClearanceAnalyzer
from .run_output import enable_timestamped_report_runs
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

__version__ = "0.4.38"