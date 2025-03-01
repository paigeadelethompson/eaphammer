#!/usr/bin/env python3
import os
import sys

from settings import settings

def exit_if_not_root():

    if os.getuid() != 0:
        sys.exit("[!} Error: this script must be run as root.")

def read_deps_file(deps_file):
    with open(deps_file) as fd:
        return ' '.join([ line.strip() for line in fd ])

def main(): 

    exit_if_not_root()
                    

    default_wordlist = os.path.join(settings.dict['paths']['directories']['wordlists'], settings.dict['core']['eaphammer']['general']['default_wordlist'])

    wordlist_source = settings.dict['core']['eaphammer']['general']['wordlist_source']

    root_dir = settings.dict['paths']['directories']['root']
    local_dir = settings.dict['paths']['directories']['local']

    openssl_source = settings.dict['core']['eaphammer']['general']['openssl_source']
    openssl_version = settings.dict['core']['eaphammer']['general']['openssl_version']
    openssl_build_options = settings.dict['core']['eaphammer']['general']['openssl_build_options']
    openssl_build_prefix = os.path.join(local_dir, 'openssl/local')

    openssl_bin = settings.dict['paths']['openssl']['bin']
    dh_file = settings.dict['paths']['certs']['dh']

    if input('Important: it is highly recommended that you run "apt -y update" and "apt -y upgrade" prior to running this setup script. Do you wish to proceed? Enter [y/N]: ').lower() != 'y':
        sys.exit('Aborting.')
    print()


    print('\n[*] Removing stub files...\n')
    os.system('find {} -type f -name \'stub\' -exec rm -f {{}} +'.format(root_dir))
    print('\ncomplete!\n')


    print('\n[*] Installing Parot dependencies...\n')
    os.system('apt -y install %s' % read_deps_file('parot-dependencies.txt'))
    print('\n[*] complete!\n')

    print('\n[*] Installing Python dependencies...\n')
    os.system('python3 -m pip install -r pip.req')
    print('\n[*] complete!\n')
    

    print('\n[*] Downloading OpenSSL_{}...\n'.format(openssl_version.replace('.', '_')))
    os.system('wget {} -O {}/openssl.tar.gz'.format(openssl_source, local_dir))
    print('\n[*] complete!\n')

    print('\n[*] Extracting OpenSSL_{}...\n'.format(openssl_version.replace('.', '_')))
    os.system('cd {} && tar xzf openssl.tar.gz'.format(local_dir))
    os.system('mv {}/openssl-OpenSSL_{} {}/openssl'.format(local_dir, openssl_version.replace('.', '_'), local_dir))
    os.system('cd {} && rm -f openssl.tar.gz'.format(local_dir))
    print('\n[*] complete!\n')

    print('\n[*] Compiling OpenSSL locally to avoid interfering with system install...\n')
    os.system('cd {}/openssl && ./config --prefix={} enable-ssl2 enable-ssl3 enable-ssl3-method enable-des enable-rc4 enable-weak-ssl-ciphers no-shared'.format(local_dir, openssl_build_prefix))
    os.system('cd {}/openssl && make'.format(local_dir))
    os.system('cd {}/openssl && make install_sw'.format(local_dir))
    print('\n[*] complete!\n')

    print('\n[*] Create DH parameters file with default length of 2048...\n')
    os.system('{} dhparam -out {} 2048'.format(openssl_bin, dh_file))
    print('\ncomplete!\n')

    print('\n[*] Compiling hostapd...\n')
    os.system("cd %s && cp defconfig .config" % settings.dict['paths']['directories']['hostapd'])
    os.system("cd %s && make hostapd-eaphammer_lib" % settings.dict['paths']['directories']['hostapd'])
    print('\n[*] complete!\n')

    print('\n[*] Compiling hcxtools...\n')
    os.system("cd %s && make" % settings.dict['paths']['directories']['hcxtools'])
    print('\n[*] complete!\n')

    print('\n[*] Compiling hcxdumptool...\n')
    os.system("cd %s && make" % settings.dict['paths']['directories']['hcxdumptool'])
    print('\n[*] complete!\n')

    print('\n[*] Downloading default wordlist...\n')
    os.system("wget %s -O %s.tar.gz" % (wordlist_source, default_wordlist))
    print('\n[*] complete!\n')

    print('\n[*] Extracting default wordlist...\n')
    os.system("cd %s && tar xzf %s.tar.gz" % (settings.dict['paths']['directories']['wordlists'], default_wordlist))
    print('\n[*] complete!\n')

    print('\n[*] Retrieving Responder from teh interwebz...\n')
    os.system("cd %s && git clone https://github.com/lgandx/Responder.git" % (settings.dict['paths']['directories']['local']))
    print('\n[*] complete!\n')

    print('\n[*] Creating symlink to captive portal template directory...\n')
    os.symlink(settings.dict['paths']['wskeyloggerd']['usr_templates'],
               settings.dict['paths']['wskeyloggerd']['usr_templates_sl'])
    print('\n[*] complete!\n')

