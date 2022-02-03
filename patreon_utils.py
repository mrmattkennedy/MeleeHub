import os
import configparser
from requests import api

import patreon


#Read config file into parser
conf_reader = configparser.ConfigParser()
conf_reader.read(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'configs', 'config.cfg'))

#Get credentials
PATREON_KEY = conf_reader.get('patreon', 'api_key')



def tier_mapping(x):
    if x == 'Tier 1': return 1
    if x == 'Tier 2': return 2
    if x == 'Tier 3': return 3
    if x == 'Tier 4': return 4
    return 0

def get_emails():
    #Get these every time so its updated on each call
    api_client = patreon.API(PATREON_KEY)
    campaign_id = api_client.fetch_campaign().data()[0].id()

    #loop until there is no cursor
    all_pledges = []
    cursor = None

    while True:
        pledges_response = api_client.fetch_page_of_pledges(campaign_id, 25, cursor=cursor)
        all_pledges += pledges_response.data()
        cursor = api_client.extract_cursor(pledges_response)
        if not cursor:
            break
    
    #For each pledge, get the email, check if still active, and the tier
    pledge_info = [{
        'email': pledge.relationship('patron').attribute('email'),
        'declined_since': pledge.attribute('declined_since'),
        'tier': pledge.relationship('reward').attribute('title')
    } for pledge in all_pledges]

    #put into a list and return
    emails = {}
    for pledge in pledge_info:
        if pledge['declined_since'] == None:
            emails[pledge['email']] = tier_mapping(pledge['tier'])

    return(emails)

def get_tier_from_patreon(email):
    #Check if registered email in emails
    patreon_data = get_emails()
    if email not in patreon_data.keys():
        return 0

    return patreon_data[email]
    

if __name__ == '__main__':
    print(get_tier_from_patreon('mdkennedy03@gmail.com'))