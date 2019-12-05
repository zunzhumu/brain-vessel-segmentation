"""
This script contains the function that divides the input MRA image in small patches, predicts the patches with given
model and saves the probability matrix as nifti file.
"""


import time
import numpy as np
from Full_vasculature.Utils import config
import os
from scipy.ndimage.filters import convolve
from Unet.utils import helper


def predict_and_save(patch_size, data_dir, model, train_metadata, patch_size_z=None):
	print('________________________________________________________________________________')
	print('patient dir:', data_dir)

	# -----------------------------------------------------------
	# LOADING MODEL, IMAGE AND MASK
	# -----------------------------------------------------------	
	print('> Loading image...')
	img_mat = helper.load_nifti_mat_from_file(
		os.path.join(data_dir, '001.nii'))
	print('> Loading mask...')
	if not os.path.exists(os.path.join(data_dir, 'mask.nii')):
		avg_mat = convolve(img_mat.astype(dtype=float), np.ones((16,16,16), dtype=float)/4096, mode='constant', cval=0)
		mask_mat = np.where(avg_mat > 10.0, 1, 0)
		helper.create_and_save_nifti(mask_mat, os.path.join(data_dir, 'mask.nii'))
	else:
		mask_mat = helper.load_nifti_mat_from_file(
			os.path.join(data_dir, 'mask.nii'))

	# -----------------------------------------------------------
	# PREDICTION
	# -----------------------------------------------------------
	# the segmentation is going to be saved in this probability matrix
	prob_mat = np.zeros(img_mat.shape, dtype=np.float32)
	x_dim, y_dim, z_dim = prob_mat.shape
	
	# get the x, y and z coordinates where there is brain
	x, y, z = np.where(mask_mat > 0)
	print('x shape:', x.shape)
	print('y shape:', y.shape)
	print('z shape:', z.shape)

	# get the z slices with brain
	z_slices = np.unique(z)

	# start cutting out and predicting the patches
	starttime_total = time.time()

	if '3d' in train_metadata['params']['model']:
		x_min = 0 # min(x)
		y_min = 0 # min(y)
		z_min = 0 # min(z)
		x_max = img_mat.shape[0] # max(x)
		y_max = img_mat.shape[1] # max(y)
		z_max = img_mat.shape[2] # max(z)

		num_x_patches = np.int(np.ceil((x_max - x_min) / patch_size[0]))
		num_y_patches = np.int(np.ceil((y_max - y_min) / patch_size[0]))	
		num_z_patches = np.int(np.ceil((z_max - z_min) / patch_size_z[0]))
	
		if num_z_patches*patch_size_z[0] + (np.max(patch_size_z)-np.min(patch_size_z))//2 > img_mat.shape[2]:
			new_z = (num_z_patches-1)*patch_size_z[0] + patch_size_z[0]//2 + np.max(patch_size_z)//2 # so that we can feed sufficient patches
			temp = np.zeros((img_mat.shape[0], img_mat.shape[1], new_z))
			temp[:, :, :img_mat.shape[2]] = img_mat
			temp[:, :, img_mat.shape[2]:] = img_mat[:,:,-(new_z - img_mat.shape[2]):]
			img_mat = temp

		for ix in range(num_x_patches):
			for iy in range(num_y_patches):
				for iz in range(num_z_patches):
					# find the starting and ending x and y coordinates of given patch
					patch_start_x = patch_size[0] * ix
					patch_end_x = patch_size[0] * (ix + 1)
					patch_start_y = patch_size[0] * iy
					patch_end_y = patch_size[0] * (iy + 1)
					patch_start_z = patch_size_z[0] * iz
					patch_end_z = patch_size_z[0] * (iz + 1)
					if patch_end_x > x_max:
						patch_end_x = x_max
					if patch_end_y > y_max:
						patch_end_y = y_max
					if patch_end_z > z_max:
						patch_end_z = z_max

					# find center loc with ref. size
					center_x = patch_start_x + int(patch_size[0]/2)
					center_y = patch_start_y + int(patch_size[0]/2)
					center_z = patch_start_z + int(patch_size_z[0]/2)

					img_patches = []
					for h, size in enumerate(patch_size):
						img_patch = np.zeros((size, size, patch_size_z[h], 1))
						offset_x = 0
						offset_y = 0
						offset_z = 0
						
						# find the starting and ending x and y coordinates of given patch
						img_patch_start_x = center_x - int(size/2)
						img_patch_end_x = center_x + int(size/2)
						img_patch_start_y = center_y - int(size/2)
						img_patch_end_y = center_y + int(size/2)
						img_patch_start_z = center_z - int(patch_size_z[h]/2)
						img_patch_end_z = center_z + int(patch_size_z[h]/2)
												
						if img_patch_end_x > x_max:
							img_patch_end_x = x_max
						if img_patch_end_y > y_max:
							img_patch_end_y = y_max
						if img_patch_start_x < x_min:
							offset_x = x_min - img_patch_start_x
							img_patch_start_x = x_min							
						if img_patch_start_y < y_min:
							offset_y = y_min - img_patch_start_y
							img_patch_start_y = y_min
						if img_patch_start_z < z_min:
							offset_z = z_min - img_patch_start_z
							img_patch_start_z = z_min

						# get the patch with the found coordinates from the image matrix
						img_patch[offset_x : offset_x + (img_patch_end_x-img_patch_start_x), 
								  offset_y : offset_y + (img_patch_end_y-img_patch_start_y),
								  offset_z : offset_z + (img_patch_end_z-img_patch_start_z), 0] \
						= img_mat[img_patch_start_x: img_patch_end_x, img_patch_start_y: img_patch_end_y, img_patch_start_z:img_patch_end_z]
	
						img_patches.append(np.expand_dims(img_patch,0))
						
					# predict the patch with the model and save to probability matrix
					prob_mat[patch_start_x: patch_end_x, patch_start_y: patch_end_y, patch_start_z:patch_end_z] = (np.reshape(
						model(img_patches)[-1],
						(patch_size[0], patch_size[0], patch_size_z[0])) > config.THRESHOLD).astype(np.uint8)[:patch_end_x-patch_start_x, :patch_end_y-patch_start_y, :patch_end_z-patch_start_z]
	else:
		# proceed slice by slice
		for i in z_slices:
			print('Slice:', i)
			starttime_slice = time.time()
			slice_vox_inds = np.where(z == i)
			# find all x and y coordinates with brain in given slice
			x_in_slice = x[slice_vox_inds]
			y_in_slice = y[slice_vox_inds]
			# find min and max x and y coordinates
			slice_x_min = min(x_in_slice)
			slice_x_max = max(x_in_slice)
			slice_y_min = min(y_in_slice)
			slice_y_max = max(y_in_slice)

			# calculate number of predicted patches in x and y direction in given slice
			if isinstance(patch_size, list):
				num_of_x_patches = np.int(np.ceil((slice_x_max - slice_x_min) / patch_size[0]))
				num_of_y_patches = np.int(np.ceil((slice_y_max - slice_y_min) / patch_size[0]))			
			else:
				num_of_x_patches = np.int(np.ceil((slice_x_max - slice_x_min) / patch_size))
				num_of_y_patches = np.int(np.ceil((slice_y_max - slice_y_min) / patch_size))
			print('num x patches', num_of_x_patches)
			print('num y patches', num_of_y_patches)
			   		 
			for j in range(num_of_x_patches):
				for k in range(num_of_y_patches):
					# find the starting and ending x and y coordinates of given patch
					patch_start_x = slice_x_min + patch_size[0] * j
					patch_end_x = slice_x_min + patch_size[0] * (j + 1)
					patch_start_y = slice_y_min + patch_size[0] * k
					patch_end_y = slice_y_min + patch_size[0] * (k + 1)
					# if the dimensions of the probability matrix are exceeded shift back the last patch
					if patch_end_x > slice_x_max:
						patch_end_x = slice_x_max
					if patch_end_y > slice_y_max:
						patch_end_y = slice_y_max

					# find center loc with ref. size
					center_x = patch_start_x + int(patch_size[0]/2)
					center_y = patch_start_y + int(patch_size[0]/2)

					img_patches = []
					for h, size in enumerate(patch_size):
						img_patch = np.zeros((size, size, 1))
						offset_x = 0
						offset_y = 0
						
						# find the starting and ending x and y coordinates of given patch
						img_patch_start_x = center_x - int(size/2)
						img_patch_end_x = center_x + int(size/2)
						img_patch_start_y = center_y - int(size/2)
						img_patch_end_y = center_y + int(size/2)
												
						if img_patch_end_x > slice_x_max:
							img_patch_end_x = slice_x_max
						if img_patch_end_y > slice_y_max:
							img_patch_end_y = slice_y_max

						if img_patch_start_x < slice_x_min:
							offset_x = slice_x_min - img_patch_start_x
							img_patch_start_x = slice_x_min							
						if img_patch_start_y < slice_y_min:
							offset_y = slice_y_min - img_patch_start_y
							img_patch_start_y = slice_y_min

						# get the patch with the found coordinates from the image matrix
						img_patch[offset_x : offset_x + (img_patch_end_x-img_patch_start_x), 
								  offset_y : offset_y + (img_patch_end_y-img_patch_start_y), 0] \
						= img_mat[img_patch_start_x: img_patch_end_x, img_patch_start_y: img_patch_end_y, i]

						img_patches.append(np.expand_dims(img_patch,0))

					# predict the patch with the model and save to probability matrix
					prob_mat[patch_start_x: patch_end_x, patch_start_y: patch_end_y, i] = (np.reshape(
						model(img_patches)[-1],
						(patch_size[0], patch_size[0])) > config.THRESHOLD).astype(np.uint8)[:patch_end_x-patch_start_x, :patch_end_y-patch_start_y]

	# how long does the prediction take for a patient
	duration_total = time.time() - starttime_total
	print('prediction in total took:', (duration_total // 3600) % 60, 'hours',
		  (duration_total // 60) % 60, 'minutes',
		  duration_total % 60, 'seconds')

	return prob_mat
