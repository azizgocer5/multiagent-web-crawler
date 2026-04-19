# Development Recommendations

This document summarizes the critical issues identified in the current test report and provides recommendations for their resolution. To complete the LangGraph integration of the project and ensure the expected functionality, the following items should be addressed with priority.

## Identified Errors and Recommendations

### ERROR-1: `langgraph_crawler/graph.py` File Missing

-   **Description**: The `langgraph_crawler/graph.py` file, which should contain the main definition of the LangGraph graph and the transition logic between nodes, was not found. Without this file, the LangGraph flow cannot be created and executed.
-   **Recommendation**: Create the `langgraph_crawler/graph.py` file. Within this file, define a function named `build_graph` to initialize the `StateGraph`, add all nodes (orchestrator, crawler, indexer, monitor), and specify the transition conditions (edges) between nodes. Additionally, ensure state persistence by using `SqliteSaver`.

### ERROR-2: `langgraph_crawler/nodes/monitor.py` File Missing/Erroneous

-   **Description**: The `langgraph_crawler/nodes/monitor.py` file is incomplete and throws a `SyntaxError: unterminated string literal`. This indicates that the functionality of the monitor node is either missing or faulty.
-   **Recommendation**: Complete the `langgraph_crawler/nodes/monitor.py` file. This node should retrieve the overall status from the database (pending, processing, completed page counts) and update the `CrawlerState` to provide a general overview of the crawling process. Correct any syntax errors and ensure the file is complete.

### ERROR-3: `main.py` Lacks LangGraph Integration

-   **Description**: The `main.py` file continues to directly use the old `CrawlerService` class instead of initiating/managing LangGraph-based nodes and the graph. Consequently, CLI commands (`crawl`, `status`, `resume`) do not trigger the LangGraph flow and do not exhibit the expected multi-agent behavior.
-   **Recommendation**: Update the `main.py` file:
    1.  Initialize the LangGraph graph using the `langgraph_crawler.graph.build_graph` function.
    2.  Configure `SqliteSaver` to ensure the persistence of the LangGraph state.
    3.  Rewrite the CLI commands (`crawl`, `search`, `status`, `resume`) to trigger them via the `invoke` or `stream` methods of the LangGraph graph. Specifically, `crawl` and `resume` commands should start the graph with the appropriate initial state and manage the crawling process through LangGraph. The `search` command can directly call the `search` node.

### ERROR-4: `turkish_lower` Function Missing

-   **Description**: The existence of a `turkish_lower` function is expected in tests, but it is not defined in the current codebase (e.g., `crawler_service.py` or another utility module).
-   **Recommendation**: If Turkish character conversion (e.g., "İ" -> "i", "Ş" -> "ş") is a project requirement, add this function to an appropriate utility module (e.g., `utils.py` or within `crawler_service.py`). Otherwise, remove the test scenario that expects this function from `test_crawler.py`.

## Conclusion

Addressing the errors mentioned above is crucial for the project to successfully transition to the LangGraph architecture and fulfill its core functionality. In particular, the completion of `graph.py` and `monitor.py` files, along with the integration of `main.py` with LangGraph, will enable the system to become testable and operational.
