import streamlit as st
from flight_agent import FlightBookingAgent, BookingState
from langchain_core.messages import AIMessage, HumanMessage

# Initialize session state
if "agent" not in st.session_state:
    st.session_state.agent = FlightBookingAgent()
    st.session_state.messages = [AIMessage(content="Welcome to FlightAgent! Where would you like to go?")]

# App layout
st.set_page_config(page_title="Flight Booking Assistant", page_icon="✈️")
st.title("✈️ Flight Assistant")
st.caption("Powered by Amadeus API and Google Gemini")

# Display chat messages
for msg in st.session_state.messages:
    if isinstance(msg, AIMessage):
        with st.chat_message("assistant"):
            st.markdown(msg.content)
    elif isinstance(msg, HumanMessage):
        with st.chat_message("user"):
            st.markdown(msg.content)

# User input
if prompt := st.chat_input("Enter your travel request..."):
    # Display user message immediately
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Add to messages
    st.session_state.messages.append(HumanMessage(content=prompt))
    
    # Process with agent - show spinner during processing
    with st.spinner("Searching for flights..."):
        # Create temporary state for processing
        temp_state = {
            "messages": st.session_state.messages.copy(),
            "search_params": {},
            "flight_options": [],
            "selected_flight": None,
            "completed": False
        }
        
        # Process the input
        new_state = st.session_state.agent.process_streamlit_input(prompt, temp_state)
        
        # Update our messages with any new responses
        for msg in new_state["messages"]:
            if isinstance(msg, AIMessage) and msg not in st.session_state.messages:
                st.session_state.messages.append(msg)
                with st.chat_message("assistant"):
                    st.markdown(msg.content)

# Sidebar with reset option
with st.sidebar:
    if st.button("Reset Conversation"):
        st.session_state.clear()
        st.rerun()