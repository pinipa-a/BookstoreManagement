from owlready2 import *
from mesa import Agent, Model
from mesa.time import RandomActivation
from mesa.space import MultiGrid
import random
import re
import os

# -------------------------
# Helper utilities
# -------------------------
def iri_safe(name: str) -> str:
    """Return a string safe for ontology individual names (letters, digits, underscore)."""
    s = re.sub(r'\W+', '_', str(name))
    if re.match(r'^\d', s):
        s = "_" + s
    return s

# -------------------------
# Message Bus Class
# -------------------------
class MessageBus:
    """Central message bus for agent communication."""
    def __init__(self):
        self.messages = []

    def publish(self, msg: str, step: int = None):
        if step is not None:
            self.messages.append(f"[Step {step}] {msg}")
        else:
            self.messages.append(msg)

    def get_messages(self):
        return self.messages.copy()

# -------------------------
# Ontology creation
# -------------------------
ONTO_FILE = "bookstore_simulation.owl"
if os.path.exists(ONTO_FILE):
    try:
        os.remove(ONTO_FILE)
    except Exception:
        pass

onto = get_ontology("http://example.org/bookstore.owl")

with onto:
    class Book(Thing): pass
    class Customer(Thing): pass
    class Employee(Thing): pass
    class Order(Thing): pass
    class Inventory(Thing): pass

    # Data properties
    class hasAuthor(DataProperty, FunctionalProperty): pass
    class hasGenre(DataProperty, FunctionalProperty): pass
    class availableQuantity(DataProperty, FunctionalProperty): pass
    class hasPrice(DataProperty, FunctionalProperty): pass

    # Object properties
    class purchases(ObjectProperty): pass  # Customer -> Book
    class worksAt(ObjectProperty): pass    # Employee -> Inventory
    class includes(ObjectProperty): pass   # Order -> Book

    # Domains and ranges
    hasAuthor.domain = [Book]
    hasGenre.domain = [Book]
    availableQuantity.domain = [Book]
    hasPrice.domain = [Book]

    purchases.domain = [Customer]
    purchases.range = [Book]

    worksAt.domain = [Employee]
    worksAt.range = [Inventory]

    includes.domain = [Order]
    includes.range = [Book]

    # Inventory instance
    store_inventory = Inventory("StoreInventory")

RESTOCK_THRESHOLD = 5

# Save initial ontology
onto.save(file=ONTO_FILE)



# -------------------------
# Mesa agent classes
# -------------------------


# -------------------------
# Book agent class
# -------------------------
class BookAgent(Agent):
    def __init__(self, unique_id, model, title, genre, price, quantity):
        # Initialize the base Mesa agent
        super().__init__(unique_id, model)

        # ----------------------------
        # Core book attributes
        # ----------------------------
        self.title = title                # Title of the book
        self.genre = genre                # Genre/category of the book
        self.price = price                # Price of the book
        self.quantity = int(quantity)     # Current stock quantity

        # ----------------------------
        # Ontology individual creation
        # ----------------------------
        # Create a unique IRI-safe name for ontology individual
        name = iri_safe(f"{self.title}_{unique_id}")

        # Create a corresponding 'Book' instance in the ontology
        self.onto_book = onto.Book(name)

        # Map MAS attributes to ontology data properties
        self.onto_book.hasGenre = self.genre
        self.onto_book.hasPrice = float(self.price)
        self.onto_book.availableQuantity = int(self.quantity)

    # ----------------------------
    # Stock management behaviors
    # ----------------------------

    def reduce_stock(self, qty):
        """
        Reduce stock when a purchase occurs.
        - Ensures quantity doesn't drop below zero.
        - Updates both the internal model and the ontology.
        """
        qty = int(qty)
        if self.quantity >= qty:
            self.quantity -= qty
            self.onto_book.availableQuantity = int(self.quantity)
            return True  # Purchase successful
        return False      # Not enough stock

    def restock(self, qty):
        """
        Increase stock when restocking by an EmployeeAgent.
        - Prevents stock from exceeding 50 units (inventory cap).
        - Synchronizes with ontology individual.
        """
        qty = int(qty)
        self.quantity = min(self.quantity + qty, 50)
        self.onto_book.availableQuantity = int(self.quantity)


# -------------------------
# Customer agent class
# -------------------------
class CustomerAgent(Agent):
    def __init__(self, unique_id, model, display_id=None):
        # Initialize the base Mesa Agent
        super().__init__(unique_id, model)

        # Track books purchased by this customer (simulation-level)
        self.books_purchased = []

        # Reference to the shared message bus for agent communication/logging
        self.message_bus = model.message_bus

        # Use readable display ID for logs and ontology naming
        self.display_id = display_id if display_id is not None else unique_id

        # ----------------------------
        # Ontology individual creation
        # ----------------------------
        # Create an ontology individual representing this customer
        cname = iri_safe(f"Customer_{self.display_id}")
        self.onto_customer = onto.Customer(cname)

    # ----------------------------------------------------------
    # Main behavior executed during each simulation time step
    # ----------------------------------------------------------
    def step(self):
        """
        Customer agent behavior per time step:
        - Randomly decides whether to make a purchase.
        - Selects a random available book.
        - Reduces stock via the corresponding BookAgent.
        - Updates ontology relationships (Customer → Book → Order).
        - Publishes purchase events to the message bus.
        """

        # Purchase decision (60% chance to buy)
        will_buy = random.random() < 0.6
        if not will_buy:
            return  # Skip this step if customer decides not to buy

        # Identify all books currently in stock
        available_books = [
            agent for agent in self.model.schedule.agents
            if isinstance(agent, BookAgent) and agent.quantity > 0
        ]
        if not available_books:
            return  # Exit if no books are available

        # Choose a random book to purchase
        book = random.choice(available_books)

        # Attempt to reduce book stock by 1 unit
        if book.reduce_stock(1):
            # Record purchase in simulation memory
            self.books_purchased.append(book.title)

            # ----------------------------
            # Ontology update: Order creation
            # ----------------------------
            # Create a unique order instance in the ontology
            order_name = iri_safe(f"Order_{self.display_id}_{book.title}_{random.randint(0,9999)}")
            order = onto.Order(order_name)

            # Establish ontology relationships
            order.includes.append(book.onto_book)           # Order → includes → Book
            self.onto_customer.purchases.append(book.onto_book)  # Customer → purchases → Book

            # Publish a message to the shared bus for logging or UI updates
            msg = f"Customer {self.display_id} purchased {book.title} (Order: {order_name})"
            self.message_bus.publish(msg, step=self.model.schedule.time)


# -------------------------
# Employee agent class
# -------------------------
class EmployeeAgent(Agent):
    def __init__(self, unique_id, model, display_id=None):
        # Initialize the base Mesa Agent
        super().__init__(unique_id, model)

        # Shared message bus for inter-agent communication
        self.message_bus = model.message_bus
        
        # Use a human-readable display ID (useful in UI or logs)
        self.display_id = display_id if display_id is not None else unique_id

        # Create a corresponding Employee individual in the ontology
        ename = iri_safe(f"Employee_{self.display_id}")
        self.onto_employee = onto.Employee(ename)

        # Link employee to the store inventory in the ontology
        try:
            self.onto_employee.worksAt = [onto.store_inventory]
        except Exception:
            # Ignore linking errors (e.g., if store_inventory not yet defined)
            pass

    def step(self):
        """
        Agent's behavior per simulation step:
        - Iterates through all book instances in the ontology
        - Checks if any book’s quantity is below the restock threshold
        - Restocks by interacting with the corresponding BookAgent
        - Logs and publishes restock actions via the message bus
        """
        for b in onto.Book.instances():  # Iterate over all books in ontology
            try:
                qty = int(b.availableQuantity)  # Get current stock level
            except Exception:
                qty = 0  # Default to 0 if unavailable or invalid

            # Check for low stock condition
            if qty < RESTOCK_THRESHOLD:
                # Find the corresponding BookAgent for this ontology book
                for agent in self.model.schedule.agents:
                    if isinstance(agent, BookAgent) and agent.onto_book == b:
                        # Calculate how much to restock (e.g., up to 10 units)
                        restock_to = 10
                        restock_amount = restock_to - agent.quantity
                        
                        if restock_amount > 0:
                            # Trigger the BookAgent’s restock behavior
                            agent.restock(restock_amount)
                            
                            # Compose a human-readable message for the UI/log
                            msg = (
                                f"Employee {self.display_id} restocked "
                                f"{agent.title} by {restock_amount}. "
                                f"New qty: {agent.quantity}"
                            )

                            # Publish the message to the shared message bus
                            self.message_bus.publish(msg, step=self.model.schedule.time)


# -------------------------
# Bookstore Model
# -------------------------
class BookstoreModel(Model):
    """
    The central simulation model that manages all agents, the environment grid,
    and the execution flow of the Bookstore Multi-Agent System (MAS).

    Responsibilities:
    - Initialize all agents (Books, Customers, Employees)
    - Manage time steps and agent activation
    - Provide a shared communication channel (MessageBus)
    - Maintain ontology synchronization across agents
    """

    def __init__(self, num_customers, num_employees, books):
        # ----------------------------
        # Core simulation setup
        # ----------------------------
        self.num_customers = num_customers        # Number of customer agents
        self.num_employees = num_employees        # Number of employee agents

        # Scheduler controls activation order of agents (random each step)
        self.schedule = RandomActivation(self)

        # Spatial grid for possible agent placement (not used heavily here but supports scalability)
        self.grid = MultiGrid(10, 10, True)  # 10x10 toroidal grid

        # Centralized message bus for communication and UI event logging
        self.message_bus = MessageBus()

        # ----------------------------
        # Agent creation
        # ----------------------------
        uid = 0  # Unique ID tracker for all agents

        # Book agents (represent inventory items)
        for b in books:
            ba = BookAgent(
                uid, 
                self,
                b['title'], 
                b.get('genre', 'Unknown'),
                b.get('price', 0.0),
                b.get('quantity', 0)
            )
            self.schedule.add(ba)
            uid += 1

        # Customer agents (simulate purchasing behavior)
        for i in range(1, num_customers + 1):
            ca = CustomerAgent(uid, self, display_id=i)
            self.schedule.add(ca)
            uid += 1

        # Employee agents (simulate restocking and store management)
        for i in range(1, num_employees + 1):
            ea = EmployeeAgent(uid, self, display_id=i)
            self.schedule.add(ea)
            uid += 1

    # ----------------------------
    # Simulation step
    # ----------------------------
    def step(self):
        """
        Execute one step (tick) of the simulation.
        - Randomly activates each agent’s behavior for this time unit.
        - Automatically handles purchases, restocks, and ontology updates.
        """
        self.schedule.step()

        
