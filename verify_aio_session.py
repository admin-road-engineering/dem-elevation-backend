import sys
import inspect
import aiobotocore.session

print("--- Environment and Version ---")
print(f"Python Version: {sys.version}")
print(f"aiobotocore version: {aiobotocore.__version__}")
print(f"aiobotocore path: {aiobotocore.__file__}")

print("\n--- Session Object Analysis ---")
session = None
try:
    session = aiobotocore.session.get_session()
    print(f"Object from get_session(): {session}")
    print(f"Object type: {type(session)}")
except Exception as e:
    print(f"ERROR getting session: {e}")

if session:
    print("\n--- API Inspection ---")
    has_close = hasattr(session, 'close')
    print(f"hasattr(session, 'close'): {has_close}")

    if not has_close:
        print("\n'close' method not found. Printing all members containing 'close':")
        for name in dir(session):
            if 'close' in name.lower():
                print(f"- {name}")

    print("\n--- Full Member Listing ---")
    # Print all public methods/attributes for manual inspection
    members = [m for m in dir(session) if not m.startswith('_')]
    print(members)