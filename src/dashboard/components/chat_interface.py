import streamlit as st
from src.intelligence.ai_assistant import AIAssistant
from typing import List, Dict

class ChatInterface:
    def __init__(self, assistant: AIAssistant):
        self.assistant = assistant
        
        # Initialize chat history
        if "messages" not in st.session_state:
            st.session_state.messages = []
            # Add initial greeting
            st.session_state.messages.append({
                "role": "assistant",
                "content": "Hello! I am your AI Network Assistant. I can help you analyze anomalies, check system health, or explain root causes. How can I assist you today?"
            })

    def render(self):
        st.sidebar.markdown("---")
        st.sidebar.subheader("💬 AI Assistant")
        
        # Display chat messages
        # Using a container for chat history
        chat_container = st.sidebar.container(height=400)
        
        with chat_container:
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

        # Chat input
        if prompt := st.sidebar.chat_input("Ask about network health...", key="chat_input"):
            # Add user message to chat history
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            # Display user message in chat message container
            with chat_container:
                with st.chat_message("user"):
                    st.markdown(prompt)

            # Generate response
            response = self.assistant.generate_response(prompt)
            
            # Add assistant response to chat history
            st.session_state.messages.append({"role": "assistant", "content": response})
            
            # Display assistant response in chat message container
            with chat_container:
                with st.chat_message("assistant"):
                    st.markdown(response)
