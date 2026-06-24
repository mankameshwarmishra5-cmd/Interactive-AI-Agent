import sys
import os
from agent import InteractiveAgent

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def print_separator():
    print("-" * 60)

def main():
    clear_screen()
    print_separator()
    print("        🤖 INTERACTIVE PYTHON AGENT (CLI MODE) 🤖")
    print_separator()
    
    # Initialize the agent
    print("Initializing agent client...")
    agent = InteractiveAgent()
    
    # Report active mode
    if agent.is_simulated:
        print("\n⚠️  WARNING: Running in SIMULATION MODE.")
        print("   To enable live Gemini API, add GEMINI_API_KEY in .env and reinstall/restart.")
    else:
        print("\n✨ SUCCESS: Running in LIVE MODE (Powered by Gemini API).")
    
    print("\nCommands:")
    print("  - Type 'exit' or 'quit' to end the session.")
    print("  - Type 'clear' to reset chat history and clear screen.")
    print_separator()
    print("Agent is ready! Start chatting below:")
    print_separator()
    
    while True:
        try:
            # Get user input
            user_input = input("\nYou: ").strip()
            
            # Handle exit/quit commands
            if user_input.lower() in ["exit", "quit"]:
                print("\nGoodbye! Have a great day!")
                break
                
            # Handle clear command
            if user_input.lower() == "clear":
                agent.clear_history()
                clear_screen()
                print_separator()
                print("Chat history cleared. Start chatting:")
                print_separator()
                continue
                
            # Skip empty inputs
            if not user_input:
                continue
                
            # Send message and get response
            print("\n*Agent is thinking...*")
            response = agent.send_message(user_input)
            
            # Print response
            print_separator()
            print(response)
            print_separator()
            
        except KeyboardInterrupt:
            print("\n\nSession interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\nAn error occurred: {e}")

if __name__ == "__main__":
    main()
