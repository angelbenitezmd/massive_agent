"""Main trading loop application."""
import asyncio
import logging
import signal
import sys
from datetime import datetime

from app.core.config import get_settings
from app.core.logging_config import setup_logging
from app.agents.orchestrator import HybridOrchestrator

logger = logging.getLogger(__name__)


class TradingLoop:
    """Main trading loop application."""

    def __init__(self):
        """Initialize the trading loop."""
        self.settings = get_settings()
        self.orchestrator = None
        self.running = False

        # Setup logging
        setup_logging(
            log_level=self.settings.LOG_LEVEL,
            log_file=self.settings.LOG_FILE
        )

    async def start(self):
        """Start the trading loop."""
        logger.info("="*60)
        logger.info("AI TRADING SYSTEM STARTING")
        logger.info("="*60)
        logger.info(f"Time: {datetime.utcnow().isoformat()}")
        logger.info(f"Environment: {self.settings.ALPACA_ENV.upper()}")
        logger.info(f"Paper Trading: {self.settings.is_paper_trading}")
        logger.info(f"Watchlist: {', '.join(self.settings.watchlist)}")
        logger.info(f"Interval: {self.settings.TRADING_HYBRID_INTERVAL_SECONDS}s")
        logger.info("="*60)

        if self.settings.ALPACA_ENV == "live":
            logger.warning("⚠️"*20)
            logger.warning("LIVE TRADING MODE - REAL MONEY AT RISK")
            logger.warning("⚠️"*20)
            print("\n" + "⚠️"*20)
            print("LIVE TRADING MODE ACTIVE")
            print("Real money will be traded!")
            print("⚠️"*20 + "\n")

            # Give user chance to cancel
            print("Starting in 10 seconds... Press Ctrl+C to cancel")
            await asyncio.sleep(10)

        # Initialize orchestrator
        self.orchestrator = HybridOrchestrator()
        self.running = True

        # Start orchestrator
        try:
            await self.orchestrator.start()
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        except Exception as e:
            logger.error(f"Fatal error in trading loop: {e}", exc_info=True)
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Gracefully shutdown the trading loop."""
        logger.info("Shutting down trading loop...")
        self.running = False

        # Close connections
        if self.orchestrator:
            if hasattr(self.orchestrator.benzinga, 'http_client'):
                await self.orchestrator.benzinga.http_client.close()
            if hasattr(self.orchestrator.alpaca, 'trading_client'):
                await self.orchestrator.alpaca.trading_client.close()
            if hasattr(self.orchestrator.alpaca, 'data_client'):
                await self.orchestrator.alpaca.data_client.close()

        logger.info("Trading loop shutdown complete")

    def handle_signal(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}")
        sys.exit(0)


async def main():
    """Main entry point."""
    loop = TradingLoop()

    # Setup signal handlers
    signal.signal(signal.SIGINT, loop.handle_signal)
    signal.signal(signal.SIGTERM, loop.handle_signal)

    # Start trading loop
    await loop.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)