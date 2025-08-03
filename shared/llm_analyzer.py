import json
import logging
import os
from typing import Dict, List, Optional

from langchain.chains import LLMChain
from langchain.memory import ConversationBufferWindowMemory
from langchain_openai import ChatOpenAI
from langchain.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
    SystemMessagePromptTemplate,
)
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field


from shared.config import ConfigManager
from shared.models import Issue, IssueType, Task


class LLMAnalyzer:
    """Uses LangChain with an OpenAI LLM to analyze issues and make intelligent decisions."""

    def __init__(self, api_key: Optional[str] = None, model: str = None):
        self.logger = logging.getLogger(__name__)
        self.config = ConfigManager().config.get("llm", {})
        self.backend = self.config.get("backend", "openai")
        self.model_name = self.config.get("model_name", "gpt-3.5-turbo")
        self.max_tokens = self.config.get("max_tokens", 512)
        self.temperature = self.config.get("temperature", 0.2)
        self.model = model or self.model_name
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

        self.issue_memories = {}  # Memory per issue ID

        if self.backend != "openai":
            raise ValueError("This LLMAnalyzer is configured for OpenAI with LangChain.")

        if not self.api_key:
            self.logger.warning(
                "No OpenAI API key provided. LLM features will be disabled."
            )
            self.llm = None
        else:
            self.llm = ChatOpenAI(
                model=self.model,
                temperature=self.temperature,
                api_key=self.api_key,
                max_tokens=self.max_tokens,
            )

    def _get_issue_memory(self, issue_id: str) -> ConversationBufferWindowMemory:
        """Retrieve or create memory for a specific issue."""
        if issue_id not in self.issue_memories:
            self.issue_memories[issue_id] = ConversationBufferWindowMemory(
                k=5, memory_key="history", return_messages=True
            )
        return self.issue_memories[issue_id]

    async def analyze_issue(self, issue: Issue, available_workers: List[Dict]) -> Dict:
        """Analyze an issue and determine the best course of action."""
        if not self.llm:
            return self._fallback_analysis(issue, available_workers)

        try:
            prompt_template = self._create_analysis_prompt()
            print(f"Prompting analysis: {prompt_template}")
            memory = self._get_issue_memory(issue.issue_id)

            chain = LLMChain(llm=self.llm, prompt=prompt_template, memory=memory)

            context = self._prepare_issue_context(issue, available_workers)
            analysis_context = f"Issue Details:\n{context['issue']}\n\nAvailable Workers: {json.dumps(context['available_workers'], indent=2)}"
            raw_response = await chain.arun(analysis_context=analysis_context)

            analysis = self._parse_llm_response(raw_response)
            self.logger.info(f"LLM analysis for issue {issue.issue_id}: {analysis}")
            return analysis
        except Exception as e:
            self.logger.error(f"Error in LLM analysis: {e}")
            return self._fallback_analysis(issue, available_workers)

    async def decide_worker_assignment(
        self, task: Task, available_workers: List[Dict]
    ) -> Optional[str]:
        """Decide which worker should handle a specific task."""
        if not self.llm:
            return self._fallback_worker_selection(task, available_workers)

        try:
            prompt_template = self._create_worker_selection_prompt()
            # Worker assignment is usually a one-off decision, but we use issue memory if available
            memory = self._get_issue_memory(task.issue_id)

            chain = LLMChain(llm=self.llm, prompt=prompt_template, memory=memory)

            context = self._prepare_task_context(task, available_workers)
            worker_selection_context = f"Task: {context['task']}\n\nAvailable Workers: {json.dumps(context['available_workers'], indent=2)}"
            raw_response = await chain.arun(worker_selection_context=worker_selection_context)

            decision = self._parse_worker_selection_response(raw_response)
            self.logger.info(
                f"LLM worker selection for task {task.task_id}: {decision}"
            )
            return decision
        except Exception as e:
            self.logger.error(f"Error in LLM worker selection: {e}")
            return self._fallback_worker_selection(task, available_workers)

    async def suggest_resolution(
        self, issue: Issue, worker_id: str, worker_capabilities: Dict
    ) -> Dict:
        """Suggest a resolution strategy for an issue, using worker-specific memory."""
        if not self.llm:
            return self._fallback_resolution_suggestion(issue)

        try:
            prompt_template = self._create_resolution_prompt()
            memory = self._get_issue_memory(
                issue.issue_id
            )  # Use issue-specific memory

            chain = LLMChain(llm=self.llm, prompt=prompt_template, memory=memory)

            context = self._prepare_resolution_context(issue, worker_capabilities)
            resolution_context = f"Issue: {context['issue']}\n\nWorker Capabilities: {json.dumps(context['worker_capabilities'], indent=2)}"
            raw_response = await chain.arun(resolution_context=resolution_context)

            resolution = self._parse_resolution_response(raw_response)
            self.logger.info(
                f"LLM resolution suggestion for issue {issue.issue_id} by worker {worker_id}: {resolution}"
            )
            return resolution
        except Exception as e:
            self.logger.error(f"Error in LLM resolution suggestion: {e}")
            return self._fallback_resolution_suggestion(issue)

    def _prepare_issue_context(
        self, issue: Issue, available_workers: List[Dict]
    ) -> Dict:
        """Prepare context for issue analysis."""
        return {
            "issue": f"""
- Type: {issue.issue_type.value}
- App: {issue.app_name}
- Description: {issue.description}
- Confidence: {issue.confidence_score}
- Recent Logs: {issue.logs[-10:] if issue.logs else []}
- Context: {issue.context}""",
            "available_workers": available_workers,
        }

    def _prepare_task_context(
        self, task: Task, available_workers: List[Dict]
    ) -> Dict:
        """Prepare context for worker selection."""
        return {
            "task": f"""
- Action: {task.action.value}
- App: {task.app_name}
- Parameters: {task.parameters}
- Priority: {task.priority}""",
            "available_workers": available_workers,
        }

    def _prepare_resolution_context(
        self, issue: Issue, worker_capabilities: Dict
    ) -> Dict:
        """Prepare context for resolution suggestion."""
        return {
            "issue": f"""
- Type: {issue.issue_type.value}
- Description: {issue.description}
- App: {issue.app_name}
- Logs: {issue.logs[-5:] if issue.logs else []}""",
            "worker_capabilities": worker_capabilities,
        }

    def _create_analysis_prompt(self) -> ChatPromptTemplate:
        """Create prompt template for issue analysis."""
        return ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(
                    self._get_system_prompt()
                ),
                MessagesPlaceholder(variable_name="history"),
                HumanMessagePromptTemplate.from_template(
                    """
Analyze this runtime issue and determine the best course of action:

{analysis_context}

Please provide a JSON response with:
1. severity: "low", "medium", "high", "critical"
2. recommended_action: The required command to fix the issue. Ensure that you provide the full command for fixing the issue.
3. target_worker: worker_id or null
4. reasoning: brief explanation
5. estimated_time: minutes
6. auto_fixable: true/false
"""
                ),
            ]
        )

    def _create_worker_selection_prompt(self) -> ChatPromptTemplate:
        """Create prompt template for worker selection."""
        return ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(
                    self._get_worker_selection_system_prompt()
                ),
                MessagesPlaceholder(variable_name="history"),
                HumanMessagePromptTemplate.from_template(
                    """
Select the best worker for this task:

{worker_selection_context}

Return only the worker_id of the best worker, or "null" if no suitable worker.
"""
                ),
            ]
        )

    def _create_resolution_prompt(self) -> ChatPromptTemplate:
        """Create prompt template for resolution suggestion."""
        return ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(
                    self._get_resolution_system_prompt()
                ),
                MessagesPlaceholder(variable_name="history"),
                HumanMessagePromptTemplate.from_template(
                    """
You are a master AI giving commands to a worker process to fix a runtime issue. The worker will execute the command in the 'action' field and report back the output. Analyze the issue context and provide a command to diagnose or fix it.
Also, you can change the code and all but you need to do it from the command line through commands. Also, instead of killing other processes to resolve the issue, try a different approach.

**IMPORTANT**: Only set `"is_resolved": true` if the logs explicitly show that the problem is already fixed. Otherwise, set it to `false` so you can see the output of your command.

{resolution_context}

Provide a JSON response with:
1. action: The console command for the worker to run.
2. steps: An array of step-by-step instructions for a human operator.
3. rollback_plan: How to undo the action if it fails.
4. success_criteria: How to verify the action worked.
5. confidence: Your confidence in this action (High, Medium, Low).
6. is_resolved: boolean. Set to `true` ONLY if the logs confirm the issue is already solved. Otherwise, `false`.
"""
                ),
            ]
        )

    def _get_system_prompt(self) -> str:
        """Get system prompt for issue analysis."""
        return """You are an AI system administrator analyzing runtime issues in a distributed environment.
You need to quickly assess issues and determine the best course of action. Be concise and practical."""

    def _get_worker_selection_system_prompt(self) -> str:
        """Get system prompt for worker selection."""
        return """You are selecting the best worker for a task. Consider load, capabilities, and availability.
Return only the worker_id or null."""

    def _get_resolution_system_prompt(self) -> str:
        """Get system prompt for resolution suggestion."""
        return """You are suggesting resolution strategies for runtime issues.
Provide practical, step-by-step solutions to fix the issue."""

    def _parse_llm_response(self, response: str) -> Dict:
        """Parse LLM response for issue analysis."""
        try:
            # Try to extract JSON from response
            if "{" in response and "}" in response:
                start = response.find("{")
                end = response.rfind("}") + 1
                json_str = response[start:end]
                return json.loads(json_str)
            else:
                # Fallback parsing
                return self._fallback_analysis(None, [])
        except Exception as e:
            self.logger.error(f"Error parsing LLM response: {e}")
            return self._fallback_analysis(None, [])

    def _parse_worker_selection_response(self, response: str) -> Optional[str]:
        """Parse LLM response for worker selection."""
        response = response.strip().lower().replace('"', "")
        if "null" in response or "none" in response:
            return None
        # Extract worker_id from response
        for word in response.split():
            if "worker" in word or "-" in word:
                return word
        return response  # Return the cleaned response if a clear ID isn't found

    def _parse_resolution_response(self, response: str) -> Dict:
        """Parse LLM response for resolution suggestion."""
        try:
            if "{" in response and "}" in response:
                start = response.find("{")
                end = response.rfind("}") + 1
                json_str = response[start:end]
                return json.loads(json_str)
            else:
                return self._fallback_resolution_suggestion(None)
        except Exception as e:
            self.logger.error(f"Error parsing resolution response: {e}")
            return self._fallback_resolution_suggestion(None)

    def _fallback_analysis(
        self, issue: Optional[Issue], available_workers: List[Dict]
    ) -> Dict:
        """Fallback analysis when LLM is not available."""
        if not issue:
            return {
                "severity": "medium",
                "recommended_action": "manual_intervention",
                "target_worker": None,
                "reasoning": "LLM not available",
                "estimated_time": 5,
                "auto_fixable": False,
            }

        # Simple rule-based analysis
        if issue.issue_type == IssueType.PORT_CONFLICT:
            return {
                "severity": "medium",
                "recommended_action": "reassign_port",
                "target_worker": (
                    available_workers[0]["worker_id"] if available_workers else None
                ),
                "reasoning": "Port conflict detected",
                "estimated_time": 2,
                "auto_fixable": True,
            }
        elif issue.issue_type == IssueType.PROCESS_CRASH:
            return {
                "severity": "high",
                "recommended_action": "restart",
                "target_worker": (
                    available_workers[0]["worker_id"] if available_workers else None
                ),
                "reasoning": "Process crash detected",
                "estimated_time": 3,
                "auto_fixable": True,
            }
        else:
            return {
                "severity": "medium",
                "recommended_action": "manual_intervention",
                "target_worker": None,
                "reasoning": "Unknown issue type",
                "estimated_time": 10,
                "auto_fixable": False,
            }

    def _fallback_worker_selection(
        self, task: Task, available_workers: List[Dict]
    ) -> Optional[str]:
        """Fallback worker selection when LLM is not available."""
        if not available_workers:
            return None

        # Simple round-robin selection
        return available_workers[0]["worker_id"]

    def _fallback_resolution_suggestion(self, issue: Optional[Issue]) -> Dict:
        """Fallback resolution suggestion when LLM is not available."""
        return {
            "action": "restart",
            "steps": ["Stop the application", "Wait 5 seconds", "Start the application"],
            "rollback_plan": "Restore from backup",
            "success_criteria": "Application responds to health check",
        }
