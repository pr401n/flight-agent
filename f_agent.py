import os
import json
import time
import logging
from typing import Annotated, TypedDict, List, Optional, Dict, Any
from dataclasses import dataclass
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.tools import tool
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from amadeus import Client, ResponseError
import streamlit as st

# --- Configuration ---
load_dotenv()

class Config:
    GEMINI_MODEL = "gemini-2.0-flash"  # Updated to current model
    MAX_RECURSION = 50
    AMADEUS_CLIENT_ID = os.getenv('AMADEUS_API_KEY')
    AMADEUS_CLIENT_SECRET = os.getenv('AMADEUS_API_SECRET')
    GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
    MAX_REQUESTS_PER_MINUTE = 10  # Conservative limit to stay under quota
    REQUEST_DELAY = 6.0  # Seconds between requests

    @classmethod
    def validate(cls):
        if not all([cls.GOOGLE_API_KEY, cls.AMADEUS_CLIENT_ID, cls.AMADEUS_CLIENT_SECRET]):
            raise ValueError("Missing required environment variables")

Config.validate()

# --- Initialize Services ---
class RateLimitedLLM:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model=Config.GEMINI_MODEL,
            google_api_key=Config.GOOGLE_API_KEY,
            temperature=0.5
        )
        self.last_call_time = 0
        self.call_count = 0
    
    def invoke(self, messages):
        current_time = time.time()
        elapsed = current_time - self.last_call_time
        
        # Enforce rate limiting
        if elapsed < Config.REQUEST_DELAY:
            time.sleep(Config.REQUEST_DELAY - elapsed)
        
        if self.call_count >= Config.MAX_REQUESTS_PER_MINUTE:
            time.sleep(60)  # Wait a minute if we hit the limit
            self.call_count = 0
        
        self.last_call_time = time.time()
        self.call_count += 1
        
        return self.llm.invoke(messages)

llm = RateLimitedLLM()
amadeus = Client(
    client_id=Config.AMADEUS_CLIENT_ID,
    client_secret=Config.AMADEUS_CLIENT_SECRET
)

# --- Data Models ---
@dataclass
class FlightSegment:
    airline: str
    flight_number: str
    origin: str
    destination: str
    departure: str
    arrival: str
    duration: str

@dataclass
class FlightOption:
    id: str
    price: str
    currency: str
    segments: List[FlightSegment]
    cabin_class: str

class BookingState(TypedDict):
    messages: Annotated[List, add_messages]
    search_params: Dict[str, Any]
    flight_options: List[Dict[str, Any]]
    selected_flight: Optional[Dict[str, Any]]
    booking_in_progress: bool
    completed: bool

# --- System Prompt ---
SYSTEM_PROMPT = SystemMessage(content="""You are FlightAgent, a professional flight booking assistant. Key responsibilities:

1. Find flights using real-time data
2. Provide clear flight options
3. Collect booking details
4. Explain policies clearly

Rules:
- Be concise but thorough
- Verify details before confirming
- Stay focused on flight-related queriesy""")

# --- Flight Search Tools ---
class FlightTools:
    @staticmethod
    @tool
    def search_flights(origin: str, destination: str, departure_date: str, 
                     adults: int = 1, cabin_class: str = "ECONOMY") -> List[dict]:
        """Search real flights using Amadeus API"""
        try:
            # Cache airport codes to reduce API calls
            origin_code = FlightTools._get_airport_code(origin)
            dest_code = FlightTools._get_airport_code(destination)
            
            if not origin_code or not dest_code:
                return {"error": "Invalid airport codes"}
                
            response = amadeus.shopping.flight_offers_search.get(
                originLocationCode=origin_code,
                destinationLocationCode=dest_code,
                departureDate=departure_date,
                adults=adults,
                travelClass=cabin_class.upper(),
                max=3  # Reduced from 5 to limit data
            )
            
            if not response.data:
                return {"error": "No flights found"}
            
            return FlightTools._format_flight_results(response.data)
            
        except ResponseError as error:
            return {"error": f"API error: {error}"}
        except Exception as e:
            return {"error": f"Search failed: {str(e)}"}
    
    @staticmethod
    def _get_airport_code(location: str) -> Optional[str]:
        """Cache airport codes to minimize API calls"""
        try:
            airports = amadeus.reference_data.locations.get(
                keyword=location,
                subType="AIRPORT"
            ).data
            return airports[0]['iataCode'] if airports else None
        except:
            return None
    
    @staticmethod
    def _format_flight_results(offers: List) -> List[dict]:
        """Minimize data processing"""
        return [{
            "id": offer['id'],
            "price": offer['price']['total'],
            "currency": offer['price']['currency'],
            "segments": [{
                "airline": seg['carrierCode'],
                "flight_number": seg['number'],
                "origin": seg['departure']['iataCode'],
                "destination": seg['arrival']['iataCode'],
                "departure": seg['departure']['at'],
                "arrival": seg['arrival']['at'],
                "duration": seg['duration']
            } for seg in offer['itineraries'][0]['segments']],
            "cabin_class": offer['class'][0]
        } for offer in offers]

# --- Agent Implementation ---
class FlightBookingAgent:
    def __init__(self):
        self.tools = [FlightTools.search_flights]
        self.llm_with_tools = llm.llm.bind_tools(self.tools)
        self.graph = self._build_graph()
        self.last_tool_use = 0
    
    def _build_graph(self):
        builder = StateGraph(BookingState)
        
        builder.add_node("start", self._start_node)
        builder.add_node("chat", self._chat_node)
        builder.add_node("search", self._search_node)
        
        builder.add_edge(START, "start")
        builder.add_edge("start", "chat")
        builder.add_conditional_edges("chat", self._route_based_on_tools)
        builder.add_edge("search", "chat")
        
        return builder.compile()
    
    def _start_node(self, state: BookingState) -> BookingState:
        return {
            "messages": [SYSTEM_PROMPT, AIMessage(content="Welcome! Where would you like to fly?")],
            "search_params": {},
            "flight_options": [],
            "selected_flight": None,
            "booking_in_progress": False,
            "completed": False
        }
    
    def _chat_node(self, state: BookingState) -> BookingState:
        messages = [m for m in state["messages"] if m.content.strip()]
        
        if state.get("flight_options"):
            flights_text = self._format_flights(state["flight_options"])
            if flights_text:
                messages.append(AIMessage(content=f"Flight options:\n{flights_text}"))
        
        if not messages:
            messages.append(AIMessage(content="How can I help with your travel plans?"))
        
        try:
            response = llm.invoke(messages)
            return {"messages": [response]}
        except Exception as e:
            logging.error(f"LLM Error: {str(e)}")
            return {"messages": [AIMessage(content="Let me check that for you...")]}
    
    def _search_node(self, state: BookingState) -> BookingState:
        current_time = time.time()
        if current_time - self.last_tool_use < Config.REQUEST_DELAY:
            time.sleep(Config.REQUEST_DELAY - (current_time - self.last_tool_use))
        
        tool_msg = state["messages"][-1]
        outbound = []
        
        for tool_call in tool_msg.tool_calls:
            if tool_call["name"] == "search_flights":
                result = FlightTools.search_flights(**tool_call["args"])
                
                if "error" in result:
                    outbound.extend([
                        ToolMessage(
                            content=json.dumps(result),
                            name=tool_call["name"],
                            tool_call_id=tool_call["id"],
                        ),
                        AIMessage(content=f"Error: {result['error']}")
                    ])
                else:
                    state["flight_options"] = result
                    outbound.append(
                        ToolMessage(
                            content=json.dumps({"count": len(result)}),
                            name=tool_call["name"],
                            tool_call_id=tool_call["id"],
                        )
                    )
                self.last_tool_use = time.time()
        
        return state | {"messages": outbound}
    
    def _route_based_on_tools(self, state: BookingState) -> str:
        if state.get("completed"):
            return END
        
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls"):
            for tool_call in last_msg.tool_calls:
                if tool_call["name"] == "search_flights":
                    return "search"
        return "chat"
    
    def _format_flights(self, flights: List[Dict]) -> str:
        """Optimized flight formatting"""
        return "\n".join(
            f"{i}. {f['segments'][0]['airline']} {f['segments'][0]['flight_number']} "
            f"({f['segments'][0]['origin']}→{f['segments'][0]['destination']}) "
            f"{f['price']} {f['currency']}"
            for i, f in enumerate(flights, 1)
        )
    
    def process_streamlit_input(self, user_input: str, state: Dict) -> Dict:
        """Handle user input with rate limit awareness"""
        if not user_input.strip():
            return state
            
        state["messages"].append(HumanMessage(content=user_input))
        
        try:
            new_state = self.graph.invoke(state, {"recursion_limit": Config.MAX_RECURSION})
            
            last_ai_msg = next(
                (m.content for m in reversed(new_state["messages"]) 
                if isinstance(m, AIMessage) and m.content.strip()),
                None
            )
            
            if last_ai_msg:
                return {
                    "messages": state["messages"] + [AIMessage(content=last_ai_msg)],
                    "search_params": new_state.get("search_params", {}),
                    "flight_options": new_state.get("flight_options", []),
                    "selected_flight": new_state.get("selected_flight"),
                    "booking_in_progress": new_state.get("booking_in_progress", False),
                    "completed": new_state.get("completed", False)
                }
            return state
        except Exception as e:
            logging.error(f"Processing error: {str(e)}")
            return {
                "messages": state["messages"] + [
                    AIMessage(content="Please give me a moment and try again.")
                ],
                "status": "error"
            }

# --- Streamlit App ---
def main():
    st.set_page_config(page_title="Flight Agent", page_icon="✈️", layout="wide")
    st.title("✈️ Smart Flight Assistant")
    
    # Initialize session state
    if "agent" not in st.session_state:
        st.session_state.agent = FlightBookingAgent()
        st.session_state.chat_state = {
            "messages": [AIMessage(content="Welcome! Where shall we fly today?")],
            "search_params": {},
            "flight_options": [],
            "selected_flight": None,
            "booking_in_progress": False,
            "completed": False
        }
    
    # Display chat
    for msg in st.session_state.chat_state["messages"]:
        role = "assistant" if isinstance(msg, AIMessage) else "user"
        st.chat_message(role).write(msg.content)
    
    # User input
    if prompt := st.chat_input("Your travel request..."):
        if not prompt.strip():
            st.warning("Please enter a valid request")
            return
            
        with st.spinner("Processing..."):
            st.session_state.chat_state = st.session_state.agent.process_streamlit_input(
                prompt,
                st.session_state.chat_state
            )
        
        # Display latest response
        last_msg = st.session_state.chat_state["messages"][-1]
        if isinstance(last_msg, AIMessage):
            st.chat_message("assistant").write(last_msg.content)
    
    # Sidebar controls
    with st.sidebar:
        st.header("Controls")
        if st.button("🔄 Reset Conversation"):
            st.session_state.clear()
            st.rerun()
        st.info("Note: API calls are rate limited for reliability")

if __name__ == "__main__":
    main()
