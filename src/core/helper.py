from random_word import RandomWords
import re
import ipaddress

class Helper():
    def get_random_word(self):
        r = RandomWords()
        return r.get_random_word()

    def format_version(self, input_string):
        version_number = input_string.lstrip("v")
        formatted_version = re.sub(r"\.", r"\\.", version_number)
        return formatted_version

    def get_oke_image(self, source, shape, kubernetes_version):
        version = self.format_version(kubernetes_version)
        if re.match(r"^VM\.Standard\.A\d+\.Flex", shape):
            pattern = f"(Oracle-Linux).*?(aarch64).*?({version})"
        elif re.match(r".*GPU.*", shape):
            pattern = f"(Oracle-Linux).*?(GPU).*?({version})"
        else:
            pattern = rf"(Oracle-Linux)-(?!.*?(?:GPU|aarch64)).*?({version})"
        return list(filter(lambda x: re.search(pattern, x["source_name"]), source))[0][
            "image_id"
        ]

    def get_ads(self, ads, net):
        z = []
        for ad in ads:
            z.append({"availability_domain": str(
                ad["name"]), "subnet_id": net})
        return z

    def calculate_subnets(self, cidr, num_subnets):
        supernet = ipaddress.ip_network(cidr)
        new_prefix_length = supernet.prefixlen
        while (2 ** (new_prefix_length - supernet.prefixlen)) < num_subnets:
            new_prefix_length += 1
        subnets = list(supernet.subnets(new_prefix=new_prefix_length))
        subnet_strings = [str(subnet) for subnet in subnets[:num_subnets]]
        return subnet_strings