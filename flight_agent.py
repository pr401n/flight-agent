from dotenv import load_dotenv
from typing import Annotated, Literal, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from typing_extensions import TypedDict
from langchain_google_genai import ChatGoogleGenerativeAI

from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode
from amadeus import ResponseError, Client
import os


load_dotenv()
config = {"recursion_limit": 100}

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash"
)

amadeus = Client(
    client_id=os.getenv('AMADEUS_API_KEY'),
    client_secret=os.getenv('AMADEUS_API_SECRET')
)

FLIGHTAGENT_SYSINT = (
    "system",
    """You are FlightAgent, a real flight booking assistant with live flight data access. Your responsibilities include:

1. Helping users find available flights based on their criteria (dates, destinations, airlines, etc.)
2. Managing multi-city itineraries
3. Collecting required traveler information (names, DOBs, passport details)
4. Processing secure payments
5. Providing booking confirmations with reference numbers

WORKFLOW RULES:
- First verify departure/return dates and destinations
- Always confirm flight details with user before booking
- Collect all passenger information before payment
- Clearly state cancellation/change policies during booking
- Only discuss flight-related matters (no off-topic conversations)

TOOLS AVAILABLE:
- search_flights(departure, destination, date, filters): Search available flights
- hold_reservation(flight_id): Temporarily hold selected flight
- add_passenger_info(passenger_details): Add traveler information
- process_payment(payment_details): Secure payment processing
- confirm_booking(): Finalize booking and get confirmation
- cancel_hold(flight_id): Release held reservation

PROTOCOLS:
1. Always verify flight details twice with user
2. Never process payment without complete passenger info
3. Provide booking reference immediately after confirmation
4. If any tools are unavailable, inform the user clearly
5. Maintain professional but friendly tone throughout"""
)

WELCOME_MSG = (
    "Welcome to FlightAgent! how can I help you today?"
)
class FlightBookingState(TypedDict):
    messages: Annotated[list, add_messages]
    finished: bool



graph_builder = StateGraph(FlightBookingState)



@tool
def search_flights(
    departure: str, 
    destination: str, 
    date: str, 
    passengers: int = 1,
    return_date: Optional[str] = None
) -> str:
    """Search for available flights between airports on specific dates.
    
    Args:
        departure: IATA code of departure airport (e.g. 'JFK')
        destination: IATA code of destination airport (e.g. 'LHR')
        date: Departure date in YYYY-MM-DD format
        passengers: Number of adult passengers (default 1)
        return_date: Optional return date for round trips (YYYY-MM-DD)
    
    Returns:
        Formatted string with flight options or error message
    """
    try:
        # Build search parameters
        params = {
            'originLocationCode': departure,
            'destinationLocationCode': destination,
            'departureDate': date,
            'adults': passengers
        }
        
        if return_date:
            params['returnDate'] = return_date
            params['nonStop'] = True  # Example additional parameter
        
        # Call Amadeus API
        response = amadeus.shopping.flight_offers_search.get(**params)
        
        # results
        return response.data
    
    except ResponseError as error:
        return f"Error searching flights: {error}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"
    
@tool
def hold_reservation(flight_id: str) -> str:
    """Temporarily hold a selected flight reservation."""
    try:
        response = amadeus.booking.flight_orders.post(
            flight_offers=[{'id': flight_id}]
        )
        return f"Flight held successfully. Reservation ID: {response['data']['id']}"
    except ResponseError as error:
        return f"Error holding flight: {error}"

@tool
def add_passenger_info(passenger_details: dict) -> str:
    """Add traveler information for booking."""
    # Implement passenger info collection
    return "Passenger information added successfully"

@tool
def process_payment(payment_details: dict) -> str:
    """Process payment for the flight booking."""
    # Implement payment processing
    return "Payment processed successfully"

@tool
def confirm_booking() -> str:
    """Finalize the booking and get confirmation."""
    # Implement booking confirmation
    return "Booking confirmed. Reference: ABC123"

@tool
def cancel_hold(flight_id: str) -> str:
    """Release a held flight reservation."""
    try:
        amadeus.booking.flight_orders(flight_id).delete()
        return "Hold cancelled successfully"
    except ResponseError as error:
        return f"Error cancelling hold: {error}"
    


def human_node(state: FlightBookingState) -> FlightBookingState:
    """Display the last model message to the user, and receive the user's input."""
    last_message = state["messages"][-1]
    print("Assistant:", last_message.content)

    user_input = input("User: ")

    # If it looks like the user is trying to quit, flag the conversation
    # as over.
    if user_input in {"q", "quit", "exit", "goodbye"}:
        state["finished"] = True

    return state | {"messages": [("user", user_input)]}

def maybe_exit_human_node(state: FlightBookingState) -> Literal["chatbot", "__end__"]:
    """Route to the chatbot, unless it looks like the user is exiting."""
    if state.get("finished", False):
        return END
    else:
        return "chatbot"


def maybe_route_to_tools(state: FlightBookingState) -> Literal["tools", "human"]:
    """Route between human or tool nodes based on flight tool calls."""
    if not (msgs := state.get("messages", [])):
        raise ValueError(f"No messages found when parsing state: {state}")

    msg = msgs[-1]

    # Check for standard tool calls (e.g., flight search)
    if hasattr(msg, "tool_calls") and len(msg.tool_calls) > 0:
        return "tools"
    else:
        return "human"


def chatbot_with_tools(state: FlightBookingState) -> FlightBookingState:
    """Flight booking chatbot with tools integration."""

    if state["messages"]:
        # Include flight-specific system instructions
        new_output = llm_with_tools.invoke([FLIGHTAGENT_SYSINT] + state["messages"])
    else:
        new_output = AIMessage(content=WELCOME_MSG)

    return state | {"messages": [new_output]}

    


def chatbot(state: FlightBookingState):
    if state['messages']:
        message_history = [FLIGHTAGENT_SYSINT]+state["messages"]
        return {"messages":[llm.invoke(message_history)]}
    
    else:
        # If there are no messages, start with the welcome message.
        new_output = AIMessage(content=WELCOME_MSG)

    return state | {"messages": [new_output]}


# Define the tools and create a "tools" node.
tools = [search_flights, hold_reservation, add_passenger_info, process_payment, confirm_booking, cancel_hold]
tool_node = ToolNode(tools)

# Attach the tools to the model so that it knows what it can call.
llm_with_tools = llm.bind_tools(tools)
 
graph_builder.add_node("chatbot", chatbot_with_tools)
graph_builder.add_node("human", human_node)
graph_builder.add_node("tools", tool_node)

graph_builder.add_edge(START, "chatbot")
graph_builder.add_edge("tools", "chatbot")
graph_builder.add_conditional_edges("human", maybe_exit_human_node)
graph_builder.add_conditional_edges("chatbot", maybe_route_to_tools)


graph = graph_builder.compile()
state = graph.invoke({"messages": []}, config)



