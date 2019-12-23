#!/usr/bin/env python3
"""Create openvpn certifcate for server and client

Usage:
  wasy.py generate-certs
  wasy.py cleanup-certs
  wasy.py get-server-config
  wasy.py get-client-config [--client=<name>]
  wasy.py create-client-config [--client=<name>]
  wasy.py (-h | --help)

Options:
  -h --help     Show this screen.
"""
import subprocess
import os
import zipfile
import datetime
import jinja2
import base64
import shutil
from docopt import docopt
import sys

sys.path.append(os.path.abspath(__file__))


class Wasy():
    def __init__(self, config_dir='/tmp/test1'):
        self.version = '1.0.1'
        self.config_dir = config_dir
        self.env = os.environ
        self.country = os.getenv('WASY_COUNTRY', 'IS')
        self.state = os.getenv('WASY_STATE', 'NA')
        self.city = os.getenv('WASY_CITY', 'Reykjavik')
        self.org = os.getenv('WASY_ORG', 'AtHome')
        self.email = os.getenv('WASY_EMAIL', 'admin@mikkari.net')
        self.cn_server = os.getenv('WASY_CN_SERVER', 'vpn-server.mikkari.net')
        self.cn_client = os.getenv('WASY_CN_CLIENT', 'vpn-client.mikkari.net')
        self.openvpn_server = os.getenv('OPENVPN_SERVER', 'localhost')
        self.openvpn_port = os.getenv('OPENVPN_PORT', '1194')
        self.openvpn_proto = os.getenv('OPENVPN_PROTO', 'udp')
        self.base_path = os.path.join(self.config_dir, 'wasy-ca')
        self.certs_path = os.path.join(self.config_dir, 'wasy-ca/new_certs')
        self.keys_path = os.path.join(self.config_dir, 'wasy-ca/keys')
        self.csr_path = os.path.join(self.config_dir, 'wasy-ca/csr')
        self.crt_path = os.path.join(self.config_dir, 'wasy-ca/crt')
        self.ta_key = os.path.join(self.config_dir, 'wasy-ca/ta.key')
        self.revoke_path = os.path.join(self.config_dir, 'wasy-ca/revoke')
        self.openssl_conf = os.path.join(self.config_dir, 'openssl.cnf')
        self.env['WASY_PATH'] = self.base_path

    def get_ca_subj(self):
        return '/C={}/ST={}/L={}/O={}/emailAddress={}'.format(self.country,
                                                              self.state,
                                                              self.city,
                                                              self.org,
                                                              self.email)

    def get_server_subj(self):
        return '/C={}/ST={}/O={}/CN={}/emailAddress={}'.format(self.country,
                                                               self.state,
                                                               self.org,
                                                               self.cn_server,
                                                               self.email)

    def get_client_subj(self, cn_client='test-vpnclient.mikkari.net'):
        return '/C={}/ST={}/O={}/CN={}/emailAddress={}'.format(self.country,
                                                               self.state,
                                                               self.org,
                                                               cn_client,
                                                               self.email)

    def generate_ta(self):
        openvpn = shutil.which("openvpn")
        if openvpn == None:
            raise RuntimeError('Can not find openvpn in path!!!')
        if not os.path.isfile(self.ta_key):
            cmds = [openvpn,
                    '--genkey',
                    '--secret',
                    self.ta_key
                    ]
            print(cmds)
            subprocess.call(cmds)
        else:
            raise RuntimeError('{} exists, already configures.'.format('ta.key'))

    def make_config_dirs(self):
        os.mkdir(self.base_path, 0o770)
        os.mkdir(self.certs_path, 0o770)
        os.mkdir(self.keys_path, 0o770)
        os.mkdir(self.csr_path, 0o770)
        os.mkdir(self.crt_path, 0o770)
        os.mkdir(self.revoke_path, 0o770)
        with open(os.path.join(self.base_path, 'index.txt'), 'w') as f:
            f.write('')
        f.close()
        with open(os.path.join(self.base_path, 'serial'), 'w') as f:
            f.write('01')
        f.close()

    def make_ca_key_cert(self):
        cmds = ['openssl',
                'req',
                '-new',
                '-newkey',
                'rsa:4096',
                '-days',
                '3650',
                '-nodes',
                '-x509',
                '-extensions',
                'easyrsa_ca',
                '-keyout',
                os.path.join(self.base_path, 'ca.key'),
                '-out',
                os.path.join(self.base_path, 'ca.crt'),
                '-subj',
                self.get_ca_subj(),
                '-config',
                self.openssl_conf]
        subprocess.call(cmds, env=self.env)

    def make_server_key_cert(self):
        cmds = ['openssl',
                'req',
                '-new',
                '-nodes',
                '-config',
                self.openssl_conf,
                '-extensions',
                'server',
                '-keyout',
                os.path.join(self.keys_path, 'server.key'),
                '-out',
                os.path.join(self.csr_path, 'server.csr'),
                '-subj',
                self.get_server_subj()]
        subprocess.call(cmds, env=self.env)
        cmds = ['openssl',
                'ca',
                '-batch',
                '-config',
                self.openssl_conf,
                '-extensions',
                'server',
                '-out',
                os.path.join(self.crt_path, 'server.crt'),
                '-in',
                os.path.join(self.csr_path, 'server.csr')]
        subprocess.call(cmds, env=self.env)

    def create_cert_client(self, client_name):
        if len(client_name) > 64:
            return 'client cn name can not be longer then 64...'
        if os.path.isfile(os.path.join(self.keys_path, '{}.key'.format(client_name))):
            return 'client exists, revoke or choose another client name (CN)'
        cmds = ['openssl',
                'req',
                '-new',
                '-nodes',
                '-config',
                self.openssl_conf,
                '-keyout',
                os.path.join(self.keys_path, '{}.key'.format(client_name)),
                '-out',
                os.path.join(self.csr_path, '{}.csr'.format(client_name)),
                '-subj',
                self.get_client_subj(client_name)]
        subprocess.call(cmds, env=self.env)
        cmds = ['openssl',
                'ca',
                '-batch',
                '-config',
                self.openssl_conf,
                '-out',
                os.path.join(self.crt_path, '{}.crt'.format(client_name)),
                '-in',
                os.path.join(self.csr_path, '{}.csr'.format(client_name))]
        subprocess.call(cmds, env=self.env)
        return '{} created.'.format(client_name)

    def revokce_cert_client(self, client_name):
        fdate = datetime.datetime.now().strftime('%Y%m%d_%H%M')
        cmds = ['openssl',
                'ca',
                '-config',
                self.openssl_conf,
                '-revoke',
                os.path.join(self.crt_path, '{}.crt').format(client_name)]
        subprocess.call(cmds, env=self.env)
        zf = zipfile.ZipFile(os.path.join(self.revoke_path, '{}_{}.zip'.format(client_name, fdate)), mode='w')
        try:
            zf.write(os.path.join(self.crt_path, '{}.crt'.format(client_name)))
            zf.write(os.path.join(self.csr_path, '{}.csr'.format(client_name)))
            zf.write(os.path.join(self.keys_path, '{}.key'.format(client_name)))
        except:
            None
        finally:
            os.remove(os.path.join(self.crt_path, '{}.crt'.format(client_name)))
            os.remove(os.path.join(self.csr_path, '{}.csr'.format(client_name)))
            os.remove(os.path.join(self.keys_path, '{}.key'.format(client_name)))
        return '{} revoked..'.format(client_name)

    def gen_dh_parama(self):
        # Generate DH parameters
        cmds = ['openssl',
                'dhparam',
                '-out',
                os.path.join(self.base_path, 'dh2048.pem'),
                '2048']
        subprocess.call(cmds, env=self.env)

    def make_crl(self):
        cmds = ['openssl',
                'ca',
                '-config',
                self.openssl_conf,
                '-gencrl',
                '-out',
                os.path.join(self.base_path, 'ca.crl')]
        subprocess.call(cmds, env=self.env)

    def make_ovpn(self, client_name):
        ca_data = open(os.path.join(self.base_path, 'ca.crt'), "r").read().splitlines()
        key_data = open(os.path.join(self.keys_path, '{}.key'.format(client_name)), "r").read().splitlines()
        crt_data = open(os.path.join(self.crt_path, '{}.crt'.format(client_name)), "r").read().splitlines()
        try:
            j2_env = jinja2.Environment(loader=jinja2.FileSystemLoader(self.config_dir),
                                        trim_blocks=True)
            ret = j2_env.get_template('template.ovpn').render(ca_cert=ca_data,
                                                        key_client=key_data,
                                                        cert_client=crt_data,
                                                        openvpn_server=self.openvpn_server,
                                                        openvpn_port=self.openvpn_port,
                                                        openvpn_proto=self.openvpn_proto)
        except: ## Fallback to localath
            j2_env = jinja2.Environment(loader=jinja2.FileSystemLoader('/code'),
                                        trim_blocks=True)
            ret = j2_env.get_template('template.ovpn').render(ca_cert=ca_data,
                                                              key_client=key_data,
                                                              cert_client=crt_data,
                                                              openvpn_server=self.openvpn_server,
                                                              openvpn_port=self.openvpn_port,
                                                              openvpn_proto=self.openvpn_proto)
        return ret


    def get_ta(self, b64=True):
        ta = open(os.path.join(self.ta_key), "r").read()  # .splitlines()
        data = ''
        for line in ta:
            data = data + line
        if b64:
            return base64.b64encode(data.encode())
        else:
            return data

    def get_server_key(self, b64=True):
        keys = open(os.path.join(self.keys_path, 'server.key'), "r").read()  # .splitlines()
        data = ''
        for line in keys:
            data = data + line
        if b64:
            return base64.b64encode(data.encode())
        else:
            return data

    def get_server_crt(self, b64=True):
        crt = open(os.path.join(self.crt_path, 'server.crt'), "r").read()  # .splitlines()
        data = ''
        for line in crt:
            data = data + line
        if b64:
            return base64.b64encode(data.encode())
        else:
            return data

    def get_ca(self, b64=True):
        ca = open(os.path.join(self.base_path, 'ca.crt'), "r").read()  # .splitlines()
        data = ''
        for line in ca:
            data = data + line
        print(data)
        if b64:
            return base64.b64encode(data.encode())
        else:
            return data

    def get_dh(self, b64=True):
        dh = open(os.path.join(self.base_path, 'dh2048.pem'), "r").read()  # .splitlines()
        data = ''
        for line in dh:
            data = data + line
        if b64:
            return base64.b64encode(data.encode())
        else:
            return data

    def get_crl(self, b64=True):
        crl = open(os.path.join(self.base_path, 'ca.crl'), "r").read()  # .splitlines()
        data = ''
        for line in crl:
            data = data + line
        if b64:
            return base64.b64encode(data.encode())
        else:
            return data

    def get_index_txt(self):
        """V 270411233003Z  01 unknown /C=IS/ST=NA/O=AtHome/CN=vpn-server.mikkari.net/emailAddress=admin@mikkari.net"""
        index = open(os.path.join(self.base_path, 'index.txt'), "r").read().splitlines()
        data = {}
        data['clients'] = []
        for line in index:
            s = line.split('\t')
            data['clients'].append(
                {'status': s[0], 'expire': self.date_format(s[1]), 'revoke': self.date_format(s[2]), 'serial': s[3],
                 'filename': s[4], 'name': s[5]})
        return data

    def date_format(self, cd):
        if len(cd) < 10:
            return ""
        else:
            return "20{}-{}-{} {}:{}:{}".format(cd[0:2], cd[2:4], cd[4:6], cd[6:8], cd[8:10], cd[10:12])

    def create(self):
        self.make_config_dirs()
        self.generate_ta()
        self.make_ca_key_cert()
        self.make_server_key_cert()
        self.create_cert_client('init-client')
        self.revokce_cert_client('init-client')
        self.make_crl()
        self.gen_dh_parama()

    def get_server_config(self):
        ca = self.get_ca().decode()
        server = self.get_server_crt().decode()
        key = self.get_server_key().decode()
        dh = self.get_dh().decode()
        crl = self.get_crl().decode()
        ta = self.get_ta().decode()
        print(f"ENV OVPN_CA {ca}")
        print(f"ENV OVPN_SERVER {server}")
        print(f"ENV OVPN_KEY {key}")
        print(f"ENV OVPN_DH {dh}")
        print(f"ENV OVPN_CRL {crl}")
        print(f"ENV OVPN_TA {ta}")

    def cleanup(self):
        shutil.rmtree(os.path.join(self.config_dir, 'wasy-ca') )





def main():
    args = docopt(__doc__)

    if args['generate-certs']:
        w = Wasy('./conf')
        w.create()

    if args['cleanup-certs']:
        w = Wasy('./conf')
        w.cleanup()

    if args['create-client-config']:
        w = Wasy('./conf')
        name = args['--client']
        if name:
            w.create_cert_client(name)
        else:
            w.create_cert_client('vpn-test')
        f = open(f"{name}.ovpn", "w")
        f.writelines(w.make_ovpn(name))
        f.close()

    if args['get-client-config']:
        w = Wasy('./conf')
        name = args['--client']
        if not name:
           name =  "vpn-test"
        f = open(f"{name}.ovpn", "w")
        f.writelines(w.make_ovpn(name))
        f.close()

    if args['get-server-config']:
        w = Wasy('./conf')
        w.get_server_config()

if __name__ == '__main__':
    main()

