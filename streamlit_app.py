import streamlit as st
from Bookstore_management_system_simulation import BookstoreModel, onto, iri_safe
import pandas as pd
import os

# -------------------------
# Page Config
# -------------------------
st.set_page_config(page_title="Bookstore MAS", layout="wide")
st.title("📚 Bookstore MAS with Ontology Integration")

# -------------------------
# Sidebar: Add new books
# -------------------------
st.sidebar.header("Add a New Book")
new_title = st.sidebar.text_input("Book Title")
new_genre = st.sidebar.text_input("Genre", value="Unknown")
new_price = st.sidebar.number_input("Price", min_value=0.0, value=10.0)
new_quantity = st.sidebar.number_input("Quantity", min_value=0, value=5)

if "new_books" not in st.session_state:
    st.session_state.new_books = []

if st.sidebar.button("Add Book"):
    if new_title.strip():
        st.session_state.new_books.append({
            "title": new_title.strip(),
            "genre": new_genre.strip(),
            "price": new_price,
            "quantity": int(new_quantity)
        })
        st.sidebar.success(f"Book '{new_title.strip()}' added!")

# -------------------------
# Simulation Controls
# -------------------------
st.header("Simulation Controls")
num_customers = st.number_input("Number of Customers", min_value=1, max_value=20, value=6)
num_employees = st.number_input("Number of Employees", min_value=1, max_value=5, value=2)
steps_to_run = st.number_input("Steps to Run at Once", min_value=1, max_value=50, value=5)


col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("Initialize Bookstore"):
        # Default books
        default_books = [
            {"title": "Brave New World", "genre": "Dystopian", "price": 9.99, "quantity": 10},
            {"title": "The Great Gatsby", "genre": "Classic", "price": 12.50, "quantity": 8},
            {"title": "Harry Potter and the Sorcerer's Stone", "genre": "Fantasy", "price": 15.20, "quantity": 5},
            {"title": "Foundation", "genre": "Science Fiction", "price": 18.75, "quantity": 2},
            {"title": "Jane Eyre", "genre": "Romance", "price": 10.00, "quantity": 6},
            {"title": "Lord of the Flies", "genre": "Classic", "price": 11.50, "quantity": 4},
        ]
        # Combine with user-added books
        all_books = default_books + st.session_state.new_books
        st.session_state.model = BookstoreModel(
            num_customers=num_customers,
            num_employees=num_employees,
            books=all_books
        )
        st.session_state.step = 0
        st.success("Bookstore initialized!")

with col2:
    if st.button("Run Next Step") and "model" in st.session_state:
        st.session_state.step += 1
        st.session_state.model.step()
        st.success(f"Step {st.session_state.step} completed!")

with col3:
    if st.button(f"Run {steps_to_run} Steps") and "model" in st.session_state:
        for _ in range(steps_to_run):
            st.session_state.model.step()
            st.session_state.step += 1
        st.success(f"Ran {steps_to_run} steps! Current step: {st.session_state.step}")

with col4:
    # Save the ontology before download
    onto.save(file="bookstore_simulation.owl")
    if os.path.exists("bookstore_simulation.owl"):
        with open("bookstore_simulation.owl", "rb") as f:
            owl_data = f.read()
        st.download_button(
            label="Download OWL File",
            data=owl_data,
            file_name="bookstore_simulation.owl",
            mime="application/rdf+xml"
        )
    else:
        st.info("Ontology file not found. Initialize the bookstore first.")

# -------------------------
# Main Display with Inventory, Purchases, and Message Log
# -------------------------
if "model" in st.session_state:
    col_left, col_right = st.columns([3, 1])  

    # ----------------- Left Column -----------------
    with col_left:
        # Inventory Table
        st.header("📦 Current Inventory")
        inventory_data = []
        for b in onto.Book.instances():
            qty = int(b.availableQuantity) if b.availableQuantity else 0
            price = f"{float(b.hasPrice):.2f}" if b.hasPrice else "0.00"
            genre = b.hasGenre if b.hasGenre else "Unknown"
            inventory_data.append({
                "Book": b.name.replace("_", " "),
                "Genre": genre,
                "Price": price,
                "Quantity": qty
            })
        df_inventory = pd.DataFrame(inventory_data)

        def highlight_restock(row):
            if row["Quantity"] < 5:
                return ['background-color: #FF6666'] * len(row)
            else:
                return [''] * len(row)

        st.dataframe(df_inventory.style.apply(highlight_restock, axis=1))

        # Customer Purchases
        st.header("🛒 Customer Purchases")
        purchases_data = []
        total_income = 0.0
        for c in onto.Customer.instances():
            purchases = []
            for p in c.purchases:
                purchases.append(p.name.replace("_", " "))
                price = f"{float(b.hasPrice):.2f}" if b.hasPrice else "0.00"
                total_income += float(price)
            purchases_data.append({
                "Customer": c.name.replace("_", " "),
                "Purchases": ", ".join(purchases) if purchases else "-"
            })

        df_purchases = pd.DataFrame(purchases_data)
        st.dataframe(df_purchases)

        st.subheader(f"💰 Total Income: ${total_income:.2f}")

    # ----------------- Right Column -----------------
    with col_right:
        st.header("📢 Message Bus Logs")
        messages = st.session_state.model.message_bus.get_messages()
        if messages:
            log_container = st.container()
            with log_container:
                for msg in reversed(messages):  
                    if "purchased" in msg:
                        st.markdown(f"<span style='color:green'>{msg}</span>", unsafe_allow_html=True)
                    elif "restocked" in msg:
                        st.markdown(f"<span style='color:orange'>{msg}</span>", unsafe_allow_html=True)
                    else:
                        st.write(msg)
        else:
            st.info("No messages yet.")
