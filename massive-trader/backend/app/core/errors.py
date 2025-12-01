"""Custom exception classes for the trading system."""
from typing import Optional, Dict, Any


class TradingSystemError(Exception):
    """Base exception for all trading system errors."""
    pass


class BenzingaAPIError(TradingSystemError):
    """Error from Benzinga API."""
    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class AlpacaAPIError(TradingSystemError):
    """Error from Alpaca API."""
    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class RiskEngineError(TradingSystemError):
    """Error from risk engine."""
    pass


class InsufficientBuyingPowerError(RiskEngineError):
    """Not enough buying power for trade."""
    pass


class MaxDrawdownExceededError(RiskEngineError):
    """Daily max drawdown exceeded."""
    pass


class SignalScoreTooLowError(RiskEngineError):
    """Signal score below minimum threshold."""
    pass


class ExecutionError(TradingSystemError):
    """Error during trade execution."""
    pass


class AIAgentError(TradingSystemError):
    """Error from AI agent processing."""
    pass


class ConfigurationError(TradingSystemError):
    """Configuration or environment error."""
    pass