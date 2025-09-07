from src import ownable_rescue

choice = input("""Scripts available:
          
    1: Ownable Contract Rescue
               
Choose a script: """)

match choice:
    case "1":
        ownable_rescue.rescue()
    case _:
        print("❌ Invalid Choice")
