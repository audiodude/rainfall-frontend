sudo ./uwsgi --plugin emperor_mongodb --emperor "mongodb://127.0.0.1:27017,emperor.vassals,{enabled:1}"
