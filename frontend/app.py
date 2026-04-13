import streamlit as st
import requests
import json

API_URL = "http://fastapi:8000"

st.title("Trip Planner AI")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = None

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("How can I help you plan your trip?"):
    # Display user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Get assistant response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                response = requests.post(
                    f"{API_URL}/api/chat",
                    json={
                        "message": prompt,
                        "session_id": st.session_state.session_id
                    },
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()
                
                assistant_message = data["response"]
                st.session_state.session_id = data["session_id"]
                
                st.markdown(assistant_message)
                st.session_state.messages.append({"role": "assistant", "content": assistant_message})
                
            except requests.exceptions.RequestException as e:
                st.error(f"Error: {str(e)}")

# Display map if itinerary is available
if st.session_state.session_id:
    try:
        session_response = requests.get(f"{API_URL}/api/session/{st.session_state.session_id}")
        if session_response.status_code == 200:
            session_data = session_response.json()
            if session_data.get('has_itinerary') and session_data.get('map_data'):
                map_data = session_data['map_data']
                st.subheader("📍 Route Map")
                
                # Display map using Streamlit's built-in map with OpenStreetMap
                if map_data.get('waypoints'):
                    waypoints = map_data['waypoints']
                    
                    # Extract coordinates for map center
                    if waypoints:
                        lats = [wp['coordinates'][0] for wp in waypoints]
                        lons = [wp['coordinates'][1] for wp in waypoints]
                        center_lat = sum(lats) / len(lats)
                        center_lon = sum(lons) / len(lons)
                        
                        # Create map data for Streamlit
                        map_data_display = []
                        for wp in waypoints:
                            map_data_display.append({
                                'lat': wp['coordinates'][0],
                                'lon': wp['coordinates'][1],
                                'name': wp['name']
                            })
                        
                        # Display map
                        st.map(map_data_display, zoom=12)
                        
                        # Display route info
                        if map_data.get('total_distance_km'):
                            st.info(f"🚗 Total Distance: {map_data['total_distance_km']:.1f} km")
                        if map_data.get('total_duration_minutes'):
                            st.info(f"⏱️ Estimated Time: {map_data['total_duration_minutes']} min")
    except Exception as e:
        st.warning(f"Could not load map: {str(e)}")

# Sidebar with session info
with st.sidebar:
    st.header("Session Info")
    if st.session_state.session_id:
        st.write(f"Session ID: {st.session_state.session_id}")
        
        # Get session details
        try:
            session_response = requests.get(f"{API_URL}/api/session/{st.session_state.session_id}")
            if session_response.status_code == 200:
                session_data = session_response.json()
                st.write(f"Created: {session_data['created_at']}")
                st.write(f"Last activity: {session_data['last_activity_at']}")
                st.write(f"Has itinerary: {session_data['has_itinerary']}")
        except:
            pass
    
    st.header("Actions")
    if st.button("Clear History"):
        st.session_state.messages = []
        st.session_state.session_id = None
        st.rerun()
