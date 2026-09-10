"""ODB++ net-to-net clearance analyzer."""

from .analyzer import ClearanceAnalyzer
from .run_output import enable_timestamped_report_runs
from .gui_zone1_default import install_zone1_default_gui_patch
from .gui_tab_layout import install_report_tab_layout_patch
from .gui_multi_zone import install_multi_zone_support
from .gui_zones_scroll import install_zones_tab_scroll_support
from .gui_zone_reset_value import install_zone_reset_value_support
from .gui_zone_matrix_mask import install_zone_matrix_duplicate_mask_support
from .gui_zone_visualization import install_zone_visualization_support
from .gui_zone_button_visibility import install_zone_button_visibility_support
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
install_report_tab_layout_patch()
install_multi_zone_support()
install_zones_tab_scroll_support()
install_zone_reset_value_support()
install_zone_matrix_duplicate_mask_support()
install_zone_visualization_support()
install_zone_button_visibility_support()

__version__ = "0.4.58"
