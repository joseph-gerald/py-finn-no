from finn import FinnSession

session = FinnSession("6vAI_121JltEHV1VWuZ7s7gIWXvXvqbb2x8XdL1Jg2iL9ANUux1YKcXRLqSyqpuz")
info = session.get_account_info()

print(info)
"""
{
    'email': 'contact@jooo.tech',
    'password': '********',
    'phone': '+4712345678',
    'name': 'Joseph Gerald',
    'display_name': 'Joseph G',
    'year_of_birth': '2008',
    'gender': 'Mann',
    'address': '3611 Kongsberg, Norway',
    'postal_code': '3611',
    'postal_name': 'Kongsberg',
    'country': 'Norge'
}
"""