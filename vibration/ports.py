"""Structural interfaces: ordinary Python objects can implement these ports."""
from typing import Protocol, Mapping, Any
from .contracts import AnalysisResult


class BearingProvider(Protocol):
    def frequencies(self, id: str, rpm: float) -> Mapping[str,float]: ...


class ResultStage(Protocol):
    def __call__(self, result: AnalysisResult) -> Mapping[str,Any]: ...


class WindowStage(ResultStage,Protocol):
    """Optional hook; values is a read-only, calibrated N x C NumPy view."""
    def analyze_window(self,result:AnalysisResult,values:Any) -> Mapping[str,Any]: ...


class ResultSink(Protocol):
    def __call__(self, result: AnalysisResult) -> None: ...
