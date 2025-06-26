import re
import time
from typing import List, Dict, Optional
from shared.models import Issue, IssueType
from shared.utils import generate_id


class LogParser:
    """Parser for analyzing application logs and detecting issues."""
    
    def __init__(self):
        # Define error patterns for different issue types
        self.error_patterns = {
            IssueType.PORT_CONFLICT: [
                r"port.*in use|Port.*in use",
                r"address already in use|Address already in use",
                r"bind.*failed|Bind.*failed",
                r"EADDRINUSE"
            ],
            IssueType.PROCESS_CRASH: [
                r"segmentation fault|Segmentation fault",
                r"killed|Killed",
                r"abort|Abort",
                r"core dumped|Core dumped",
                r"exit.*code.*[1-9]|Exit.*code.*[1-9]"
            ],
            IssueType.DEPENDENCY_MISSING: [
                r"module not found|Module not found",
                r"package not found|Package not found",
                r"import.*error|Import.*error",
                r"cannot find|Cannot find",
                r"no such file|No such file"
            ],
            IssueType.TIMEOUT: [
                r"timeout|Timeout|TIMEOUT",
                r"connection.*timed out|Connection.*timed out",
                r"request.*timed out|Request.*timed out",
                r"operation.*timed out|Operation.*timed out"
            ],
            IssueType.MEMORY_LOW: [
                r"out of memory|Out of memory",
                r"memory.*exhausted|Memory.*exhausted",
                r"heap.*space|Heap.*space",
                r"gc.*overhead|GC.*overhead"
            ],
            IssueType.CPU_HIGH: [
                r"cpu.*overload|CPU.*overload",
                r"high.*cpu.*usage|High.*CPU.*usage",
                r"cpu.*throttling|CPU.*throttling"
            ],
            IssueType.CONFIG_ERROR: [
                r"configuration.*error|Configuration.*error",
                r"config.*invalid|Config.*invalid",
                r"missing.*config|Missing.*config",
                r"invalid.*parameter|Invalid.*parameter"
            ]
        }
        
        # Define severity levels
        self.severity_levels = {
            IssueType.PORT_CONFLICT: 0.7,
            IssueType.PROCESS_CRASH: 0.9,
            IssueType.DEPENDENCY_MISSING: 0.8,
            IssueType.TIMEOUT: 0.6,
            IssueType.MEMORY_LOW: 0.8,
            IssueType.CPU_HIGH: 0.5,
            IssueType.CONFIG_ERROR: 0.7
        }
    
    def parse_logs_for_issues(self, logs: List[str], app_name: str) -> List[Issue]:
        """Parse logs and detect issues."""
        issues = []
        
        for i, log_line in enumerate(logs):
            for issue_type, patterns in self.error_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, log_line, re.IGNORECASE):
                        issue = self._create_issue(
                            app_name=app_name,
                            issue_type=issue_type,
                            description=self._extract_description(log_line),
                            logs=logs[max(0, i-5):i+6],  # Include context
                            line_number=i
                        )
                        issues.append(issue)
                        break  # Only create one issue per line
        
        return issues
    
    def _create_issue(self, app_name: str, issue_type: IssueType, 
                     description: str, logs: List[str], line_number: int) -> Issue:
        """Create an issue object."""
        return Issue(
            issue_id=generate_id(),
            worker_id="",  # Will be set by worker agent
            app_name=app_name,
            issue_type=issue_type,
            description=description,
            confidence_score=self.severity_levels.get(issue_type, 0.5),
            logs=logs,
            context={
                "line_number": line_number,
                "detected_at": time.time(),
                "pattern_matched": True
            },
            timestamp=time.time()
        )
    
    def _extract_description(self, log_line: str) -> str:
        """Extract a meaningful description from a log line."""
        # Remove timestamps and common prefixes
        cleaned_line = re.sub(r'^\d{4}-\d{2}-\d{2}.*?\]\s*', '', log_line)
        cleaned_line = re.sub(r'^\[.*?\]\s*', '', cleaned_line)
        
        # Truncate if too long
        if len(cleaned_line) > 200:
            cleaned_line = cleaned_line[:197] + "..."
        
        return cleaned_line.strip()
    
    def analyze_error_frequency(self, logs: List[str], time_window: int = 300) -> Dict[str, int]:
        """Analyze frequency of different error types in recent logs."""
        current_time = time.time()
        recent_logs = []
        
        # Extract timestamps and filter recent logs
        for log_line in logs:
            timestamp_match = re.search(r'\[(\d+\.?\d*)\]', log_line)
            if timestamp_match:
                try:
                    log_time = float(timestamp_match.group(1))
                    if current_time - log_time <= time_window:
                        recent_logs.append(log_line)
                except ValueError:
                    continue
        
        # Count error types
        error_counts = {}
        for log_line in recent_logs:
            for issue_type, patterns in self.error_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, log_line, re.IGNORECASE):
                        error_counts[issue_type.value] = error_counts.get(issue_type.value, 0) + 1
                        break
        
        return error_counts
    
    def detect_startup_issues(self, logs: List[str]) -> List[Issue]:
        """Detect issues specifically during application startup."""
        startup_issues = []
        
        # Look for startup-specific patterns
        startup_patterns = {
            IssueType.PORT_CONFLICT: [
                r"failed.*to.*bind.*port|Failed.*to.*bind.*port",
                r"port.*already.*in.*use|Port.*already.*in.*use"
            ],
            IssueType.DEPENDENCY_MISSING: [
                r"module.*not.*found.*at.*startup|Module.*not.*found.*at.*startup",
                r"missing.*dependency.*at.*startup|Missing.*dependency.*at.*startup"
            ],
            IssueType.CONFIG_ERROR: [
                r"invalid.*config.*at.*startup|Invalid.*config.*at.*startup",
                r"missing.*config.*at.*startup|Missing.*config.*at.*startup"
            ]
        }
        
        # Only check first 50 lines for startup issues
        startup_logs = logs[:50]
        
        for i, log_line in enumerate(startup_logs):
            for issue_type, patterns in startup_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, log_line, re.IGNORECASE):
                        issue = self._create_issue(
                            app_name="",  # Will be set by caller
                            issue_type=issue_type,
                            description=f"Startup issue: {self._extract_description(log_line)}",
                            logs=startup_logs[max(0, i-2):i+3],
                            line_number=i
                        )
                        startup_issues.append(issue)
                        break
        
        return startup_issues
    
    def get_issue_summary(self, logs: List[str]) -> Dict:
        """Get a summary of issues found in logs."""
        issues = self.parse_logs_for_issues(logs, "")
        error_frequency = self.analyze_error_frequency(logs)
        
        return {
            "total_issues": len(issues),
            "issue_types": list(set(issue.issue_type.value for issue in issues)),
            "error_frequency": error_frequency,
            "most_common_issue": max(error_frequency.items(), key=lambda x: x[1])[0] if error_frequency else None,
            "severity_distribution": {
                "high": len([i for i in issues if i.confidence_score >= 0.8]),
                "medium": len([i for i in issues if 0.5 <= i.confidence_score < 0.8]),
                "low": len([i for i in issues if i.confidence_score < 0.5])
            }
        } 