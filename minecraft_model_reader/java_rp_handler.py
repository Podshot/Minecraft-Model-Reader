import os
import json
import copy
from typing import List, Union, Dict, Tuple
from PIL import Image
import numpy
from .api import base_api
try:
	from amulet.api.block import Block
except:
	from .api.block import Block
from . import java_block_model


class JavaRP(base_api.BaseRP):
	"""A class to hold the bare bones information about the resource pack.
	Holds the pack format, description and if the pack is valid.
	This information can be used in a viewer to display the packs to the user."""
	def __init__(self, resource_pack_path: str):
		base_api.BaseRP.__init__(self)
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


class JavaRPHandler(base_api.BaseRPHandler):
	"""A class to load and handle the data from the packs.
	Packs are given as a list with the later packs overwriting the earlier ones."""
	def __init__(self, resource_packs: Union[JavaRP, List[JavaRP]]):
		base_api.BaseRPHandler.__init__(self)
		if isinstance(resource_packs, list) and all(isinstance(path, JavaRP) for path in resource_packs):
			self._packs = resource_packs
		elif isinstance(resource_packs, JavaRP):
			self._packs = [resource_packs]
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

		for pack in self._packs:
			# pack_format=2 textures/blocks, textures/items - case sensitive
			# pack_format=3 textures/blocks, textures/items - lower case
			# pack_format=4 textures/block, textures/item

			if pack.valid_pack and os.path.isdir(os.path.join(pack.root_dir, 'assets')):
				for namespace in os.listdir(os.path.join(pack.root_dir, 'assets')):
					if os.path.isdir(os.path.join(pack.root_dir, 'assets', namespace)):
						if pack.pack_format >= 2:
							if os.path.isdir(os.path.join(pack.root_dir, 'assets', namespace, 'textures')):
								for root, _, files in os.walk(os.path.join(pack.root_dir, 'assets', namespace, 'textures')):
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
		# TODO: add some logic here to convert the block to Java blockstate format if it is not already
		if block.blockstate not in self._cached_models:
			self._cached_models[block] = java_block_model.get_model(self, block, face_mode)
		return copy.deepcopy(self._cached_models[block])
