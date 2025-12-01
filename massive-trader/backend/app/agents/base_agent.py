"""Base agent class for AI multi-agent system."""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from langchain.chat_models import ChatAnthropic
from langchain.schema import SystemMessage, HumanMessage
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel

from app.core.config import get_settings
from app.models.signals import AgentScore

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base class for all AI agents."""

    def __init__(self, name: str, model: Optional[str] = "claude-3-opus-20240229"):
        """
        Initialize base agent.

        Args:
            name: Agent name for logging
            model: LLM model to use
        """
        self.name = name
        self.settings = get_settings()

        # Initialize LLM
        self.llm = ChatAnthropic(
            anthropic_api_key=self.settings.ANTHROPIC_API_KEY,
            model=model,
            temperature=0.3,  # Lower temperature for more consistent outputs
            max_tokens=1000
        )

        # Output parser for structured responses
        self.output_parser = PydanticOutputParser(pydantic_object=AgentScore)

        logger.info(f"Initialized {name} agent with model {model}")

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Get the system prompt for this agent.

        Returns:
            System prompt string
        """
        pass

    @abstractmethod
    def prepare_data(self, data: Dict[str, Any]) -> str:
        """
        Prepare input data for the agent.

        Args:
            data: Raw data to analyze

        Returns:
            Formatted data string
        """
        pass

    async def analyze(self, data: Dict[str, Any]) -> AgentScore:
        """
        Analyze data and return structured score.

        Args:
            data: Input data to analyze

        Returns:
            AgentScore with analysis results
        """
        try:
            # Prepare messages
            system_message = SystemMessage(content=self.get_system_prompt())

            # Format data for analysis
            formatted_data = self.prepare_data(data)

            # Add output format instructions
            format_instructions = self.output_parser.get_format_instructions()

            human_content = f"""
Analyze the following data and provide your assessment:

{formatted_data}

{format_instructions}

Remember to:
1. Score from 0-100 (50 is neutral)
2. Sentiment from -1 to +1
3. Confidence from 0 to 1
4. Urgency from 0 to 1
5. Include brief reasoning in notes
"""

            human_message = HumanMessage(content=human_content)

            # Get LLM response
            response = await self.llm.agenerate([[system_message, human_message]])

            # Parse response
            result = self.output_parser.parse(response.generations[0][0].text)

            logger.info(f"{self.name} analysis complete: score={result.score:.1f}, sentiment={result.sentiment:.2f}")

            return result

        except Exception as e:
            logger.error(f"Error in {self.name} analysis: {e}")
            # Return neutral score on error
            return AgentScore(
                score=50.0,
                sentiment=0.0,
                confidence=0.0,
                urgency=0.0,
                notes=f"Error in analysis: {str(e)}"
            )

    def calculate_weighted_score(
        self,
        base_score: float,
        factors: Dict[str, float]
    ) -> float:
        """
        Calculate weighted score based on multiple factors.

        Args:
            base_score: Starting score (0-100)
            factors: Dict of factor_name -> adjustment (-1 to 1)

        Returns:
            Adjusted score (0-100)
        """
        adjusted_score = base_score

        for factor_name, adjustment in factors.items():
            # Each factor can adjust score by up to 20 points
            adjusted_score += adjustment * 20

        # Clamp to 0-100 range
        return max(0, min(100, adjusted_score))