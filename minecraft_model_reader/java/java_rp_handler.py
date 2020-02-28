import os
import json
import copy
from urllib.request import urlopen
import zipfile
import io
from typing import List, Union, Dict, Tuple
from PIL import Image
import numpy
from minecraft_model_reader.api import resource_pack
try:
	from amulet.api.block import Block
except:
	from minecraft_model_reader.api.block import Block
from minecraft_model_reader.java import java_block_model
import minecraft_model_reader


class JavaRP(resource_pack.BaseRP):
	"""A class to hold the bare bones information about the resource pack.
	Holds the pack format, description and if the pack is valid.
	This information can be used in a viewer to display the packs to the user."""
	def __init__(self, resource_pack_path: str):
		resource_pack.BaseRP.__init__(self)
		assert os.path.isdir(resource_pack_path), 'The given path must be a directory'
		self._root_dir = resource_pack_path
		try:
			if os.path.isfile(os.path.join(resource_pack_path, 'pack.mcmeta')):
				with open(os.path.join(resource_pack_path, 'pack.mcmeta')) as f:
					pack_mcmeta = json.load(f)
				self._pack_format = pack_mcmeta['pack']['pack_format']
				self._pack_description = str(pack_mcmeta['pack'].get('description', ''))
				self._valid_pack = True
		except:
			pass

		if self._valid_pack:
			if os.path.isfile(os.path.join(resource_pack_path, 'pack.png')):
				self._pack_icon = os.path.join(resource_pack_path, 'pack.png')

	def __repr__(self):
		return f'JavaRP({self._root_dir})'


class JavaRPHandler(resource_pack.BaseRPHandler):
	"""A class to load and handle the data from the packs.
	Packs are given as a list with the later packs overwriting the earlier ones."""
	def __init__(self, resource_packs: Union[JavaRP, List[JavaRP]]):
		resource_pack.BaseRPHandler.__init__(self)
		if isinstance(resource_packs, list) and all(isinstance(path, JavaRP) for path in resource_packs):
			if resource_packs:
				self._packs = resource_packs
			else:
				vanilla_rp_path = os.path.join(minecraft_model_reader.path, 'resource_packs', 'java_vanilla')
				if os.path.isdir(vanilla_rp_path):
					vanilla_rp = JavaRP(vanilla_rp_path)
				else:
					vanilla_rp = None
				if vanilla_rp is None or not vanilla_rp.valid_pack:
					# download the latest server and extract the assets
					try:
						launcher_manifest = json.load(urlopen('https://launchermeta.mojang.com/mc/game/version_manifest.json'))
						new_version = launcher_manifest['latest']['release']
						version_url = next(v["url"] for v in launcher_manifest['versions'] if v['id'] == new_version)
						version_manifest = json.load(urlopen(version_url))
						version_client_url = version_manifest["downloads"]["client"]["url"]

						client = zipfile.ZipFile(io.BytesIO(urlopen(version_client_url).read()))
						for fpath in client.namelist():
							if fpath.startswith('assets/'):
								client.extract(fpath, vanilla_rp_path)
						client.extract('pack.mcmeta', vanilla_rp_path)
						client.extract('pack.png', vanilla_rp_path)

						vanilla_rp = JavaRP(vanilla_rp_path)
					except Exception as e:
						import traceback
						traceback.print_exc()
						raise Exception(f'Failed to download and extract the vanilla resource pack. Make sure you have a connection to the internet\n{e}')
				self._packs = [vanilla_rp]
			self._packs += [minecraft_model_reader.java_vanilla_fix]
		elif isinstance(resource_packs, JavaRP):
			self._packs = [resource_packs]
		else:
			raise Exception(f'Invalid format {resource_packs}')
		self.reload()

	def reload(self):
		"""Reload the resources from the resource packs.
		This clears all memory and repopulates it."""
		self.unload()

		blockstate_file_paths: Dict[Tuple[str, str], str] = {}
		model_file_paths: Dict[Tuple[str, str], str] = {}
		if os.path.isfile(os.path.join(os.path.dirname(__file__), 'transparrency_cache.json')):
			try:
				with open(os.path.join(os.path.dirname(__file__), 'transparrency_cache.json')) as f:
					self._texture_is_transparrent = json.load(f)
			except:
				pass

		self._textures[('minecraft', 'missing_no')] = self.missing_no

		for pack in self._packs:
			# pack_format=2 textures/blocks, textures/items - case sensitive
			# pack_format=3 textures/blocks, textures/items - lower case
			# pack_format=4 textures/block, textures/item
			# pack_format=5 ?

			if pack.valid_pack and os.path.isdir(os.path.join(pack.root_dir, 'assets')):
				for namespace in os.listdir(os.path.join(pack.root_dir, 'assets')):
					if os.path.isdir(os.path.join(pack.root_dir, 'assets', namespace)):
						if pack.pack_format >= 2:
							if os.path.isdir(os.path.join(pack.root_dir, 'assets', namespace, 'textures')):
								for root, _, files in os.walk(os.path.join(pack.root_dir, 'assets', namespace, 'textures')):
									if any(root.startswith(os.path.join(pack.root_dir, 'assets', namespace, 'textures', path)) for path in ['gui', 'font']):
										continue
									for f in files:
										if f.endswith('.png'):
											rel_path = os.path.relpath(os.path.join(root, f[:-4]), os.path.join(pack.root_dir, 'assets', namespace, 'textures')).replace(os.sep, '/')
										else:
											continue
										texture_path = os.path.join(root, f)
										self._textures[(namespace, rel_path)] = texture_path
										if os.stat(texture_path)[8] != self._texture_is_transparrent.get(texture_path, [0])[0]:
											texture_is_transparrent = False
											im: Image.Image = Image.open(texture_path)
											if im.mode == 'RGBA':
												alpha = numpy.array(im.getchannel('A').getdata())
												texture_is_transparrent = numpy.any(alpha != 255)

											self._texture_is_transparrent[os.path.join(root, f)] = [os.stat(texture_path)[8], bool(texture_is_transparrent)]

							if os.path.isdir(os.path.join(pack.root_dir, 'assets', namespace, 'blockstates')):
								for f in os.listdir(os.path.join(pack.root_dir, 'assets', namespace, 'blockstates')):
									if f.endswith('.json'):
										blockstate_file_paths[(namespace, f[:-5])] = os.path.join(pack.root_dir, 'assets', namespace, 'blockstates', f)

							if os.path.isdir(os.path.join(pack.root_dir, 'assets', namespace, 'models')):
								for root, _, files in os.walk(os.path.join(pack.root_dir, 'assets', namespace, 'models')):
									for f in files:
										if f.endswith('.json'):
											rel_path = os.path.relpath(os.path.join(root, f[:-5]), os.path.join(pack.root_dir, 'assets', namespace, 'models'))
											model_file_paths[(namespace, rel_path.replace(os.sep, '/'))] = os.path.join(root, f)

		with open(os.path.join(os.path.dirname(__file__), 'transparrency_cache.json'), 'w') as f:
			json.dump(self._texture_is_transparrent, f)

		for key, path in blockstate_file_paths.items():
			with open(path) as fi:
				self._blockstate_files[key] = json.load(fi)

		for key, path in model_file_paths.items():
			with open(path) as fi:
				self._model_files[key] = json.load(fi)

	def texture_is_transparrent(self, namespace: str, path: str) -> bool:
		return self._texture_is_transparrent[self._textures[(namespace, path)]][1]

	def get_model(self, block: Block, face_mode: int = 3):
		"""Get a model for a block state.
		The block should already be in the resource pack format"""
		if block not in self._cached_models:
			self._cached_models[block] = java_block_model.get_model(self, block, face_mode)
		return copy.deepcopy(self._cached_models[block])