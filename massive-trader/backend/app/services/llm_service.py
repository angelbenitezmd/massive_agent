"""LLM Service supporting Claude (Anthropic) and OpenAI models."""
import os
import json
import logging
from typing import Dict, Any, Optional, List
from enum import Enum

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    CLAUDE = "claude"
    OPENAI = "openai"


class LLMService:
    """Unified LLM service for Claude and OpenAI."""

    def __init__(self):
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.openai_key = os.getenv("OPENAI_API_KEY")

        self._anthropic_client = None
        self._openai_client = None

        # Check which providers are available
        self.has_claude = bool(self.anthropic_key and self.anthropic_key != "your_anthropic_api_key")
        self.has_openai = bool(self.openai_key and self.openai_key != "your_openai_api_key")

        logger.info(f"LLM Service initialized - Claude: {self.has_claude}, OpenAI: {self.has_openai}")

    @property
    def anthropic_client(self):
        """Lazy load Anthropic client."""
        if self._anthropic_client is None and self.has_claude:
            try:
                import anthropic
                self._anthropic_client = anthropic.Anthropic(api_key=self.anthropic_key)
            except ImportError:
                logger.warning("anthropic package not installed")
        return self._anthropic_client

    @property
    def openai_client(self):
        """Lazy load OpenAI client."""
        if self._openai_client is None and self.has_openai:
            try:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=self.openai_key)
            except ImportError:
                logger.warning("openai package not installed")
        return self._openai_client

    async def analyze_with_claude(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 1024,
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """
        Analyze using Claude.

        Args:
            system_prompt: System context
            user_prompt: User message with data
            model: Claude model to use
            max_tokens: Max response tokens
            temperature: Response randomness (0-1)

        Returns:
            Parsed JSON response or error dict
        """
        if not self.anthropic_client:
            return {"error": "Claude not available", "fallback": True}

        try:
            message = self.anthropic_client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )

            response_text = message.content[0].text

            # Try to parse as JSON
            try:
                # Find JSON in response
                if "```json" in response_text:
                    json_str = response_text.split("```json")[1].split("```")[0].strip()
                elif "```" in response_text:
                    json_str = response_text.split("```")[1].split("```")[0].strip()
                elif "{" in response_text:
                    start = response_text.index("{")
                    end = response_text.rindex("}") + 1
                    json_str = response_text[start:end]
                else:
                    json_str = response_text

                return json.loads(json_str)
            except (json.JSONDecodeError, ValueError):
                return {"raw_response": response_text, "parsed": False}

        except Exception as e:
            logger.error(f"Claude API error: {e}")
            return {"error": str(e)}

    async def analyze_with_openai(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = "gpt-4o",
        max_tokens: int = 1024,
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """
        Analyze using OpenAI.

        Args:
            system_prompt: System context
            user_prompt: User message with data
            model: OpenAI model to use
            max_tokens: Max response tokens
            temperature: Response randomness (0-1)

        Returns:
            Parsed JSON response or error dict
        """
        if not self.openai_client:
            return {"error": "OpenAI not available", "fallback": True}

        try:
            response = self.openai_client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt + "\n\nRespond in JSON format."},
                    {"role": "user", "content": user_prompt}
                ]
            )

            response_text = response.choices[0].message.content

            try:
                return json.loads(response_text)
            except json.JSONDecodeError:
                return {"raw_response": response_text, "parsed": False}

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return {"error": str(e)}

    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        prefer: LLMProvider = LLMProvider.CLAUDE,
        fallback: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Analyze with preferred provider, fallback to other if needed.

        Args:
            system_prompt: System context
            user_prompt: User message
            prefer: Preferred provider
            fallback: Whether to try other provider on failure
            **kwargs: Additional args for the provider

        Returns:
            Analysis result dict
        """
        result = None

        if prefer == LLMProvider.CLAUDE:
            if self.has_claude:
                result = await self.analyze_with_claude(system_prompt, user_prompt, **kwargs)
                if not result.get("error") and not result.get("fallback"):
                    result["provider"] = "claude"
                    return result

            if fallback and self.has_openai:
                logger.info("Falling back to OpenAI")
                result = await self.analyze_with_openai(system_prompt, user_prompt, **kwargs)
                if not result.get("error"):
                    result["provider"] = "openai"
                    return result
        else:
            if self.has_openai:
                result = await self.analyze_with_openai(system_prompt, user_prompt, **kwargs)
                if not result.get("error") and not result.get("fallback"):
                    result["provider"] = "openai"
                    return result

            if fallback and self.has_claude:
                logger.info("Falling back to Claude")
                result = await self.analyze_with_claude(system_prompt, user_prompt, **kwargs)
                if not result.get("error"):
                    result["provider"] = "claude"
                    return result

        # No LLM available
        return {
            "error": "No LLM provider available",
            "has_claude": self.has_claude,
            "has_openai": self.has_openai
        }


# Global instance
llm_service = LLMService()
