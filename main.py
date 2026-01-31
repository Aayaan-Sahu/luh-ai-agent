import os
import operator
from dotenv import load_dotenv
from typing import Annotated, List, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import tool

load_dotenv()

if not os.getenv("GOOGLE_API_KEY"):
    print("Can't find google API key")
    exit(1)
print("success")

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]

@tool
def adder(a: int, b: int) -> int:
    """Adds two integers together."""
    print(f"[SYSTEM CALL] Executing adder({a}, {b})...")
    return a + b

tools = [adder]

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")

model = llm.bind_tools(tools)

def call_model(state: AgentState):
    """
    The Brain Node.
    1. Reads the message history (Fetch).
    2. Asks the LLM what to do (Decode).
    3. Returns the new message to be appended (Write Back).
    """
    messages = state["messages"]
    response = model.invoke(messages)
    return {"messages": [response]}

tool_node = ToolNode(tools)

workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)
workflow.set_entry_point("agent")

def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    
    if last_message.tool_calls:
        return "tools"
    return END

workflow.add_conditional_edges(
    "agent",
    should_continue,
    ["tools", END]
)

workflow.add_edge("tools", "agent")

app = workflow.compile()

__name__ = "__main__"

if __name__ == "__main__":
    user_input = "What's 55 + 108"
    print(f"User: {user_input}")
    initial_state = {"messages": [HumanMessage(content=user_input)]}
    for event in app.stream(initial_state):
        
        # 'event' is a dictionary containing the node name and the state update
        # e.g., {'agent': {'messages': [AIMessage(...)]}}
        for node_name, state_update in event.items():
            print(f"\n--- Node: {node_name} ---")
            
            # Get the new message that was just created
            last_message = state_update["messages"][-1]
            
            # Check what type of message it is to print it nicely
            if node_name == "agent" and last_message.tool_calls:
                # The LLM is asking to use a tool
                call = last_message.tool_calls[0]
                print(f"👉 Agent decided to call: {call['name']} with args {call['args']}")
        
            elif last_message.content:
                # The LLM (or Tool) is outputting text
                print("Node:", node_name)
                print(f"Output: {last_message.content}")
            
            else:
                # Sometimes a tool returns raw data without text content
                print(f"Tool Result processed.")