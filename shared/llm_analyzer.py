import openai
import json
import logging
from typing import Dict, List, Optional, Tuple
from shared.models import Issue, Task, ActionType, IssueType
import os
from shared.config import ConfigManager

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
    import torch
except ImportError:
    AutoModelForCausalLM = None
    AutoTokenizer = None
    pipeline = None
    torch = None


class LLMAnalyzer:
    """Uses OpenAI LLM or local SLM to analyze issues and make intelligent decisions."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = None):
        self.logger = logging.getLogger(__name__)
        self.config = ConfigManager().config.get("llm", {})
        self.backend = self.config.get("backend", "slm-local")
        self.model_name = self.config.get("model_name", "TinyLlama/TinyLlama-1.1B-Chat-v1.0")
        self.device = self.config.get("device", "cpu")
        self.max_tokens = self.config.get("max_tokens", 512)
        self.temperature = self.config.get("temperature", 0.2)
        self.model = model or self.model_name
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._local_model = None
        self._local_tokenizer = None
        self._local_pipeline = None
        if self.backend == "openai":
            if self.api_key:
                openai.api_key = self.api_key
            else:
                self.logger.warning("No OpenAI API key provided. LLM features will be disabled.")
        elif self.backend == "slm-local":
            self._load_local_slm()

    def _load_local_slm(self):
        if not (AutoModelForCausalLM and AutoTokenizer and pipeline):
            self.logger.error("transformers not installed. Please install 'transformers' and 'torch'.")
            return
        try:
            self._local_tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._local_model = AutoModelForCausalLM.from_pretrained(self.model_name)
            self._local_pipeline = pipeline(
                "text-generation",
                model=self._local_model,
                tokenizer=self._local_tokenizer,
                device=0 if self.device == "cuda" and torch.cuda.is_available() else -1
            )
            self.logger.info(f"Loaded local SLM: {self.model_name} on {self.device}")
        except Exception as e:
            self.logger.error(f"Failed to load local SLM: {e}")
            self._local_model = None
            self._local_tokenizer = None
            self._local_pipeline = None

    async def _call_local_slm(self, prompt: str) -> str:
        if not self._local_pipeline:
            self.logger.error("Local SLM pipeline not loaded.")
            return "{}"
        try:
            outputs = self._local_pipeline(
                prompt,
                max_new_tokens=self.max_tokens,
                temperature=self.temperature,
                do_sample=True
            )
            return outputs[0]["generated_text"][len(prompt):].strip()
        except Exception as e:
            self.logger.error(f"Local SLM inference error: {e}")
            return "{}"

    async def analyze_issue(self, issue: Issue, available_workers: List[Dict]) -> Dict:
        """Analyze an issue and determine the best course of action."""
        if self.backend == "openai":
            if not self.api_key:
                return self._fallback_analysis(issue, available_workers)
            try:
                context = self._prepare_issue_context(issue, available_workers)
                prompt = self._create_analysis_prompt(context)
                response = await openai.ChatCompletion.acreate(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens
                )
                analysis = self._parse_llm_response(response.choices[0].message.content)
                self.logger.info(f"LLM analysis for issue {issue.issue_id}: {analysis}")
                return analysis
            except Exception as e:
                self.logger.error(f"Error in LLM analysis: {e}")
                return self._fallback_analysis(issue, available_workers)
        elif self.backend == "slm-local":
            context = self._prepare_issue_context(issue, available_workers)
            prompt = self._create_analysis_prompt(context)
            response = await self._call_local_slm(prompt)
            analysis = self._parse_llm_response(response)
            self.logger.info(f"SLM analysis for issue {issue.issue_id}: {analysis}")
            return analysis
        else:
            return self._fallback_analysis(issue, available_workers)
    
    async def decide_worker_assignment(self, task: Task, available_workers: List[Dict]) -> Optional[str]:
        """Decide which worker should handle a specific task."""
        if self.backend == "openai":
            if not self.api_key:
                return self._fallback_worker_selection(task, available_workers)
            try:
                context = self._prepare_task_context(task, available_workers)
                prompt = self._create_worker_selection_prompt(context)
                response = await openai.ChatCompletion.acreate(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self._get_worker_selection_system_prompt()},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=self.temperature,
                    max_tokens=200
                )
                decision = self._parse_worker_selection_response(response.choices[0].message.content)
                self.logger.info(f"LLM worker selection for task {task.task_id}: {decision}")
                return decision
            except Exception as e:
                self.logger.error(f"Error in LLM worker selection: {e}")
                return self._fallback_worker_selection(task, available_workers)
        elif self.backend == "slm-local":
            context = self._prepare_task_context(task, available_workers)
            prompt = self._create_worker_selection_prompt(context)
            response = await self._call_local_slm(prompt)
            decision = self._parse_worker_selection_response(response)
            self.logger.info(f"SLM worker selection for task {task.task_id}: {decision}")
            return decision
        else:
            return self._fallback_worker_selection(task, available_workers)
    
    async def suggest_resolution(self, issue: Issue, worker_capabilities: Dict) -> Dict:
        """Suggest a resolution strategy for an issue."""
        if self.backend == "openai":
            if not self.api_key:
                return self._fallback_resolution_suggestion(issue)
            try:
                context = self._prepare_resolution_context(issue, worker_capabilities)
                prompt = self._create_resolution_prompt(context)
                response = await openai.ChatCompletion.acreate(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self._get_resolution_system_prompt()},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=self.temperature,
                    max_tokens=400
                )
                resolution = self._parse_resolution_response(response.choices[0].message.content)
                self.logger.info(f"LLM resolution suggestion for issue {issue.issue_id}: {resolution}")
                return resolution
            except Exception as e:
                self.logger.error(f"Error in LLM resolution suggestion: {e}")
                return self._fallback_resolution_suggestion(issue)
        elif self.backend == "slm-local":
            context = self._prepare_resolution_context(issue, worker_capabilities)
            prompt = self._create_resolution_prompt(context)
            response = await self._call_local_slm(prompt)
            resolution = self._parse_resolution_response(response)
            self.logger.info(f"SLM resolution suggestion for issue {issue.issue_id}: {resolution}")
            return resolution
        else:
            return self._fallback_resolution_suggestion(issue)
    
    def _prepare_issue_context(self, issue: Issue, available_workers: List[Dict]) -> Dict:
        """Prepare context for issue analysis."""
        return {
            "issue": {
                "type": issue.issue_type.value,
                "description": issue.description,
                "app_name": issue.app_name,
                "confidence_score": issue.confidence_score,
                "logs": issue.logs[-10:] if issue.logs else [],  # Last 10 log lines
                "context": issue.context
            },
            "available_workers": available_workers,
            "timestamp": issue.timestamp
        }
    
    def _prepare_task_context(self, task: Task, available_workers: List[Dict]) -> Dict:
        """Prepare context for worker selection."""
        return {
            "task": {
                "action": task.action.value,
                "app_name": task.app_name,
                "parameters": task.parameters,
                "priority": task.priority
            },
            "available_workers": available_workers
        }
    
    def _prepare_resolution_context(self, issue: Issue, worker_capabilities: Dict) -> Dict:
        """Prepare context for resolution suggestion."""
        return {
            "issue": {
                "type": issue.issue_type.value,
                "description": issue.description,
                "app_name": issue.app_name,
                "logs": issue.logs[-5:] if issue.logs else []
            },
            "worker_capabilities": worker_capabilities
        }
    
    def _create_analysis_prompt(self, context: Dict) -> str:
        """Create prompt for issue analysis."""
        return f"""
Analyze this runtime issue and determine the best course of action:

Issue Details:
- Type: {context['issue']['type']}
- App: {context['issue']['app_name']}
- Description: {context['issue']['description']}
- Confidence: {context['issue']['confidence_score']}
- Recent Logs: {context['issue']['logs']}

Available Workers: {json.dumps(context['available_workers'], indent=2)}

Please provide a JSON response with:
1. severity: "low", "medium", "high", "critical"
2. recommended_action: "restart", "reconfigure", "reassign_port", "install_dependency", "manual_intervention"
3. target_worker: worker_id or null
4. reasoning: brief explanation
5. estimated_time: minutes
6. auto_fixable: true/false
"""
    
    def _create_worker_selection_prompt(self, context: Dict) -> str:
        """Create prompt for worker selection."""
        return f"""
Select the best worker for this task:

Task: {context['task']['action']} on {context['task']['app_name']}
Parameters: {context['task']['parameters']}
Priority: {context['task']['priority']}

Available Workers: {json.dumps(context['available_workers'], indent=2)}

Return only the worker_id of the best worker, or "null" if no suitable worker.
"""
    
    def _create_resolution_prompt(self, context: Dict) -> str:
        """Create prompt for resolution suggestion."""
        return f"""
Suggest a resolution strategy for this issue:

Issue: {context['issue']['type']} - {context['issue']['description']}
App: {context['issue']['app_name']}
Logs: {context['issue']['logs']}

Worker Capabilities: {json.dumps(context['worker_capabilities'], indent=2)}

Provide a JSON response with:
1. action: specific action to take
2. steps: array of step-by-step instructions
3. rollback_plan: how to undo if it fails
4. success_criteria: how to verify it worked
"""
    
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
Provide practical, step-by-step solutions that can be automated."""
    
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
        response = response.strip().lower()
        if "null" in response or "none" in response:
            return None
        # Extract worker_id from response
        for word in response.split():
            if "worker" in word or "-" in word:
                return word
        return None
    
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
    
    def _fallback_analysis(self, issue: Optional[Issue], available_workers: List[Dict]) -> Dict:
        """Fallback analysis when LLM is not available."""
        if not issue:
            return {
                "severity": "medium",
                "recommended_action": "manual_intervention",
                "target_worker": None,
                "reasoning": "LLM not available",
                "estimated_time": 5,
                "auto_fixable": False
            }
        
        # Simple rule-based analysis
        if issue.issue_type == IssueType.PORT_CONFLICT:
            return {
                "severity": "medium",
                "recommended_action": "reassign_port",
                "target_worker": available_workers[0]["worker_id"] if available_workers else None,
                "reasoning": "Port conflict detected",
                "estimated_time": 2,
                "auto_fixable": True
            }
        elif issue.issue_type == IssueType.PROCESS_CRASH:
            return {
                "severity": "high",
                "recommended_action": "restart",
                "target_worker": available_workers[0]["worker_id"] if available_workers else None,
                "reasoning": "Process crash detected",
                "estimated_time": 3,
                "auto_fixable": True
            }
        else:
            return {
                "severity": "medium",
                "recommended_action": "manual_intervention",
                "target_worker": None,
                "reasoning": "Unknown issue type",
                "estimated_time": 10,
                "auto_fixable": False
            }
    
    def _fallback_worker_selection(self, task: Task, available_workers: List[Dict]) -> Optional[str]:
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
            "success_criteria": "Application responds to health check"
        } 