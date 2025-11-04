import streamlit as st
import base64
from anthropic import Anthropic
import json
from io import BytesIO
from datetime import datetime
from PIL import Image
from dotenv import load_dotenv
import os

# API Configuration
load_dotenv()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
client = Anthropic(api_key=ANTHROPIC_API_KEY)

# Initialize session state
if 'leaderboard' not in st.session_state:
    st.session_state.leaderboard = {}
if 'prediction_made' not in st.session_state:
    st.session_state.prediction_made = False
if 'current_predictions' not in st.session_state:
    st.session_state.current_predictions = set()
if 'current_player' not in st.session_state:
    st.session_state.current_player = ""
if 'result_ready' not in st.session_state:
    st.session_state.result_ready = False
if 'claude_result' not in st.session_state:
    st.session_state.claude_result = None
if 'captured_image' not in st.session_state:
    st.session_state.captured_image = None
if 'input_mode' not in st.session_state:
    st.session_state.input_mode = "upload"

def encode_image_to_base64(image_file):
    return base64.b64encode(image_file.read()).decode("utf-8")

def pil_to_base64(pil_image):
    """Convert PIL image to base64 string."""
    buffer = BytesIO()
    pil_image.save(buffer, format='JPEG', quality=95)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode('utf-8')

def classify_waste(image_b64: str):
    """
    Sends the image to Claude for waste classification.
    Automatically converts the image to JPEG format if needed.
    """
    # Decode the base64 string
    image_data = base64.b64decode(image_b64)
    
    # Open the image with PIL
    image = Image.open(BytesIO(image_data))
    
    # Convert to RGB if necessary (JPEG doesn't support transparency)
    if image.mode in ('RGBA', 'LA', 'P'):
        # Create a white background
        background = Image.new('RGB', image.size, (255, 255, 255))
        if image.mode == 'P':
            image = image.convert('RGBA')
        background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
        image = background
    elif image.mode != 'RGB':
        image = image.convert('RGB')
    
    # Save as JPEG to a BytesIO buffer
    buffer = BytesIO()
    image.save(buffer, format='JPEG', quality=95)
    buffer.seek(0)
    
    # Encode back to base64
    jpeg_b64 = base64.b64encode(buffer.read()).decode('utf-8')
    
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=500,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "You are a waste-sorting assistant. "
                            "Analyze the image and identify ALL items present. If people are present, analyze the item they are holding. If it is a container ASSUME IT IS EMPTY."
                            "For each item or category of items, determine if it belongs to: trash, recycling, or compost. Prioritize analyzing and looking for items related to waste management "
                            "List all applicable waste categories present in the image. If a category is NOT applicable, do NOT include that keyword in your response."
                            "Format your response by clearly stating which categories apply (you can mention multiple), "
                            "then provide a friendly explanation of what you see and why each category is needed."
                            "If no items in the image related to waste management or recycling categories, do NOT include any of the keywords in your response."
                             
                         
                        ),
                    },
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": jpeg_b64,
                        },
                    },
                ],
            }
        ],
    )
    
    return response.content[0].text.strip()

def extract_classifications(result_text):
    """Extract all classifications from Claude's response."""
    lower = result_text.lower()
    categories = set()
    
    if "compost" in lower:
        categories.add("compost")
    if "recycling" in lower or "recycle" in lower:
        categories.add("recycling")
    if "trash" in lower or "garbage" in lower:
        categories.add("trash")
    
    return categories

def calculate_score(predicted, actual):
    """
    Calculate score based on prediction accuracy.
    - Correct predictions: +5 points each
    - Missing categories: 0 points
    - Wrong categories: -3 points each
    """
    if not predicted:
        return 0
    
    correct = predicted.intersection(actual)
    wrong = predicted.difference(actual)
    
    score = len(correct) * 5 - len(wrong) * 3
    return max(0, score)  # Minimum score is 0

def update_leaderboard(player_name, points_earned):
    """Update the leaderboard with new points."""
    if player_name in st.session_state.leaderboard:
        st.session_state.leaderboard[player_name] += points_earned
    else:
        st.session_state.leaderboard[player_name] = points_earned

def get_sorted_leaderboard():
    """Return leaderboard sorted by points."""
    return sorted(st.session_state.leaderboard.items(), key=lambda x: x[1], reverse=True)

def reset_image_state():
    """Reset all image-related states."""
    st.session_state.prediction_made = False
    st.session_state.current_predictions = set()
    st.session_state.result_ready = False
    st.session_state.claude_result = None
    st.session_state.captured_image = None

# --- Streamlit Frontend ---
st.set_page_config(page_title="Smart Waste Sorter", page_icon="♻️", layout="centered")

# Sidebar for Leaderboard
with st.sidebar:
    st.header("🏆 Leaderboard")
    
    if st.session_state.leaderboard:
        leaderboard = get_sorted_leaderboard()
        for idx, (name, score) in enumerate(leaderboard, 1):
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else "  "
            st.write(f"{medal} **{name}**: {score} points")
    else:
        st.write("No scores yet! Be the first to play!")
    
    st.divider()
    st.write("**How to Play:**")
    st.write("1. Enter your name")
    st.write("2. Upload or capture an image")
    st.write("3. Select ALL categories present")
    st.write("4. Earn 5 points per correct category")
    st.write("5. Lose 3 points per wrong category")
    
    if st.button("Reset Leaderboard"):
        st.session_state.leaderboard = {}
        st.rerun()

# Main App
st.title("Smart Waste Sorter")
st.write("Upload or capture a photo of items and select ALL waste categories present. Images may contain multiple types!")

# Player Name Input
player_name = st.text_input("Enter your name:", value=st.session_state.current_player)
if player_name:
    st.session_state.current_player = player_name

# Input mode selection
st.write("### Choose Input Method:")
col_upload, col_camera = st.columns(2)

with col_upload:
    if st.button("Upload Image", use_container_width=True, type="primary" if st.session_state.input_mode == "upload" else "secondary"):
        st.session_state.input_mode = "upload"
        reset_image_state()
        st.rerun()

with col_camera:
    if st.button("📸 Use Camera", use_container_width=True, type="primary" if st.session_state.input_mode == "camera" else "secondary"):
        st.session_state.input_mode = "camera"
        reset_image_state()
        st.rerun()

st.divider()

# Handle different input modes
current_image = None

if st.session_state.input_mode == "upload":
    uploaded_file = st.file_uploader("Upload an image", type=["jpg", "jpeg", "png"], key="file_uploader")
    if uploaded_file:
        current_image = uploaded_file
        st.image(uploaded_file, caption="Uploaded image", use_container_width=True)

elif st.session_state.input_mode == "camera":
    camera_photo = st.camera_input("Take a picture", key="camera_input")
    if camera_photo:
        current_image = camera_photo
        st.image(camera_photo, caption="Captured image", use_container_width=True)

# Process image if available
if current_image:
    # Prediction Selection with checkboxes
    if not st.session_state.prediction_made:
        st.write("### Select ALL categories present in the image:")
        st.write("*Tip: Look carefully - there may be multiple types of items!*")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            trash_selected = st.checkbox("🗑️ Trash", key="trash_check")
        with col2:
            recycling_selected = st.checkbox("♻️ Recycling", key="recycling_check")
        with col3:
            compost_selected = st.checkbox("🌱 Compost", key="compost_check")
        
        if st.button("Submit Prediction", type="primary", use_container_width=True):
            if not player_name:
                st.error("Please enter your name first!")
            else:
                # Collect selected categories
                selected = set()
                if trash_selected:
                    selected.add("trash")
                if recycling_selected:
                    selected.add("recycling")
                if compost_selected:
                    selected.add("compost")
                
                if not selected:
                    st.error("Please select at least one category!")
                else:
                    st.session_state.current_predictions = selected
                    st.session_state.prediction_made = True
                    st.session_state.result_ready = False
                    st.rerun()
    
    # Show Result
    if st.session_state.prediction_made and not st.session_state.result_ready:
        prediction_text = ", ".join([p.upper() for p in sorted(st.session_state.current_predictions)])
        st.info(f"You predicted: **{prediction_text}**")
        
        # Get base64 image
        current_image.seek(0)  
        image_b64 = encode_image_to_base64(current_image)
        
        with st.spinner("EcoPerks is analyzing all items..."):
            result = classify_waste(image_b64)
            st.session_state.claude_result = result
        
        # Determine all classifications
        actual_classifications = extract_classifications(result)
        
        # Calculate score and update leaderboard
        score = calculate_score(st.session_state.current_predictions, actual_classifications)
        if score > 0:
            update_leaderboard(player_name, score)
        
        st.session_state.result_ready = True
        st.rerun()
    
    # Display results after processing
    if st.session_state.result_ready and st.session_state.claude_result:
        prediction_text = ", ".join([p.upper() for p in sorted(st.session_state.current_predictions)])
        st.info(f"You predicted: **{prediction_text}**")
        
        result = st.session_state.claude_result
        actual_classifications = extract_classifications(result)
        
        # Calculate feedback
        correct = st.session_state.current_predictions.intersection(actual_classifications)
        missed = actual_classifications.difference(st.session_state.current_predictions)
        wrong = st.session_state.current_predictions.difference(actual_classifications)
        
        score = calculate_score(st.session_state.current_predictions, actual_classifications)
        
        # Show score breakdown
        if score > 0:
            st.success(f"You earned {score} points!")
        elif wrong:
            st.error("No points earned this round.")
        else:
            st.warning("You missed some categories!")
        
        # Detailed feedback
        col1, col2, col3 = st.columns(3)
        with col1:
            if correct:
                st.markdown("**✅ Correct:**")
                for cat in sorted(correct):
                    st.write(f"• {cat.capitalize()}")
        with col2:
            if missed:
                st.markdown("**⚠️ Missed:**")
                for cat in sorted(missed):
                    st.write(f"• {cat.capitalize()}")
        with col3:
            if wrong:
                st.markdown("**❌ Incorrect:**")
                for cat in sorted(wrong):
                    st.write(f"• {cat.capitalize()}")
        
        # Display Claude's analysis
        st.markdown("---")
        st.markdown("**EcoPerk's Analysis:**")
        
        # Color coding based on primary category
        if len(actual_classifications) > 1:
            color = "#9C27B0"  # Purple for mixed
        elif "compost" in actual_classifications:
            color = "#4CAF50"
        elif "recycling" in actual_classifications:
            color = "#2196F3"
        elif "trash" in actual_classifications:
            color = "#9E9E9E"
        else:
            color = "#FFC107"
        
        actual_text = ", ".join([c.upper() for c in sorted(actual_classifications)])
        
        st.markdown(
            f"""
            <div style='background-color:{color};padding:15px;border-radius:10px;color:white;margin-bottom:15px;'>
                <strong>Categories Present: {actual_text}</strong>
            </div>
            """,
            unsafe_allow_html=True,
        )
        
        st.markdown(
            f"""
            <div style='background-color:#f0f0f0;padding:20px;border-radius:10px;color:#333;font-size:16px;'>
                {result}
            </div>
            """,
            unsafe_allow_html=True,
        )
        
        # Reset button
        st.markdown("---")
        if st.button("🔄 Try Another Item", use_container_width=True):
            reset_image_state()
            st.rerun()

else:
    st.info("📸 Upload an image or use your camera to start playing!")