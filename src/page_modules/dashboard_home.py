"""
Dashboard Home Page - Professional ERP-style landing page.

A visually appealing dashboard that provides an overview of all available
contract analysis tools and features.
"""

import streamlit as st
from datetime import datetime

def render_dashboard_home():
    """Render the main dashboard home page."""
    
    # Main header
    st.markdown(
        """
        <div style="text-align: center; margin: 60px 0;">
            <h1 style="font-size: 4em; color: #FF6B6B; font-weight: bold; margin: 20px 0; line-height: 1.1;">
                Hi, I am Lizzy's File Analyzer.
            </h1>
            <h2 style="font-size: 3em; color: #FF6B6B; font-weight: bold; margin: 20px 0; line-height: 1.1;">
                How can I help you today?
            </h2>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    st.markdown("---")
    
    # Main features section
    st.markdown("## 🚀 Available Modules")
    
    # Modern card grid for modules
    st.markdown("""
    <style>
    .module-card {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
        padding: 2rem 1.5rem 1.5rem 1.5rem;
        margin-bottom: 1.5rem;
        min-height: 220px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        transition: all 0.3s ease;
        backdrop-filter: blur(10px);
        cursor: pointer;
    }
    .module-card:hover {
        background: rgba(255, 255, 255, 0.08);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
        transform: translateY(-4px);
        border-color: rgba(255, 107, 107, 0.3);
    }
    .module-card:active {
        transform: translateY(-2px);
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
    }
    .module-icon {
        font-size: 2.5em;
        margin-bottom: 0.5em;
        filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.2));
    }
    .module-title {
        font-size: 1.3em;
        font-weight: 600;
        margin-bottom: 0.3em;
        text-align: center;
        color: inherit;
    }
    .module-desc {
        opacity: 0.7;
        font-size: 1em;
        text-align: center;
        margin-bottom: 0;
        color: inherit;
    }
    
    /* Light mode specific styles */
    @media (prefers-color-scheme: light) {
        .module-card {
            background: rgba(255, 255, 255, 0.8);
            border-color: rgba(0, 0, 0, 0.1);
            box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
        }
        .module-card:hover {
            background: rgba(255, 255, 255, 0.95);
            box-shadow: 0 4px 24px rgba(0, 0, 0, 0.12);
        }
    }
    </style>
    """, unsafe_allow_html=True)

    card_data = [
        {
            "icon": "📦",
            "title": "Product Request Detection",
            "desc": "",
            "key": "btn_product",
            "page": "product_detection"
        },
        {
            "icon": "🧾",
            "title": "Invoice Request Detection",
            "desc": "",
            "key": "btn_invoice",
            "page": "invoice_detection"
        },
        {
            "icon": "📋",
            "title": "Detailed Contract Analysis",
            "desc": "",
            "key": "btn_detailed",
            "page": "detailed_analysis"
        },
        {
            "icon": "🎯",
            "title": "Miller's Use Cases",
            "desc": "",
            "key": "btn_miller",
            "page": "miller_cases"
        },
    ]

    cols = st.columns(4)
    for i, card in enumerate(card_data):
        with cols[i % 4]:
            # Use st.button with custom styling to make entire card clickable
            if st.button(
                f"{card['icon']}\n\n**{card['title']}**\n\n{card['desc']}", 
                key=card['key'], 
                use_container_width=True,
                type="secondary"
            ):
                st.session_state.current_page = card['page']
                st.rerun()
    st.markdown("<br>", unsafe_allow_html=True)