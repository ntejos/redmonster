#
# multifit.py
#
# Module of routines for enabling fitting of multiple
# spectra at one time
#
# bolton@utah@iac 2014junio
#

import numpy as n
from redmonster.math import misc
import copy

# These globals almost certainly belong somewhere else:

gal_emline_wave = n.asarray([
    3727.0917,
    3729.8754,
    4102.8916,
    4341.6843,
    4862.6830,
    4960.2949,
    5008.2397,
    6549.8590,
    6564.6140,
    6585.2685,
    6718.2943,
    6732.6782])

gal_emline_name = n.asarray([
    '[O_II] 3725',
    '[O_II] 3727',
    'H_delta',
    'H_gamma',
    'H_beta',
    '[O_III] 4959',
    '[O_III] 5007',
    '[N_II] 6548',
    'H_alpha',
    '[N_II] 6583',
    '[S_II] 6716',
    '[S_II] 6730'])

c_kms = 2.99792458e5

def multi_projector(wavebound_list, sigma_list, coeff0, coeff1):
    """
    Function to take a list of spectro wavelength baselines and
    associated instrumental dispersion parameters and return
    a list of projection matrices from a common uniform
    log-lambda grid into the frame of the individual exposures,
    including broadening by instrumental dispersion.

    Arguments:
      wavebound_list: List of 1D vectors each containing the
        pixel boundaries of the individual spectra.  Each
        vector is taken to be of length npix_j + 1, where
        npix_j is the number of pixels in the j'th spectrum
        Must be monotonically increasing or something will crash.
      sigma_list: List of instrumental Gaussian sigma dispersion
        parameter vectors.  Each vector to be of length npix_j.
        Should be in same units as wavebound_list.
      coeff0: log10-angstroms (vacuum, rest frame) of the zeroth
        pixel of the constant log10-lambda grid from which the
        projection matrices should broadcast to the individual
        spectra.
      coeff1: delta log10-angstroms per pixel of the constant
        log10-lambda grid from which the projection matrices
        should broadcast to the individual spectra.

    Returns:
      (matrix_list, idx_list, nsamp_list)
    where
      matrix_list is a list of (scipy.sparse) projection
        matrices that broadcast from the model baseline to
        the individual spectrum baselines, and
      idx_list is a list of the indices of the zeroth pixel of
        the model-grid matrix dimensions within the baseline
        specified by the input coeff0/coeff1 values, and
      nsamp_list is a list of the number of model-space
        sample-pixels encompassed by each matrix.

    To make that more explicit,
      matrix_list[j] will have formal dimensions
        npix_j X nsamp_j
      and the dimesion of length nsamp_j aligns with
        loglam[idx_list[j]:idx_list[j]+nsamp_list[j]]
      where
        loglam = coeff0 + coeff1 + n.arange(...)
      is the log10-lambda baseline of the model grid.

      This all ensures that we don't waste time on any
      dimensional coverage that we don't need, and that
      we can slide things in redshift by pixel-shifting
      the projection matrices within the models.

    Written: bolton@utah@iac 2014junio
    """
    # Number of spectra:
    nspec = len(wavebound_list)
    # Number of pixels in each spectrum:
    npix_list = [len(this_sigma) for this_sigma in sigma_list]
    # Wavelengths of a 6-sigma buffer at the high and low ends:
    wavelim_lo = [wavebound_list[k][0] - 10. * sigma_list[k][0] for k in xrange(nspec)]
    wavelim_hi = [wavebound_list[k][-1] + 10. * sigma_list[k][-1] for k in xrange(nspec)]
    # Translate these into indices within the nominal full model baseline
    idx_list = [int(round((n.log10(this_wave) - coeff0) / coeff1)) for this_wave in wavelim_lo]
    idx_hi = [int(round((n.log10(this_wave) - coeff0) / coeff1)) for this_wave in wavelim_hi]
    nsamp_list = [idx_hi[k] - idx_list[k] + 1 for k in xrange(nspec)]
    # Compute the nominal wavelength arrays for the spectra:
    wave_list = [0.5 * (this_bound[1:] + this_bound[:-1]) for this_bound in wavebound_list]
    # Compute the various model-space wavelength baselines that we need:
    modloglam_list = [coeff0 + coeff1 * (n.arange(nsamp_list[k]) + idx_list[k]) for k in xrange(nspec)]
    modlogbound_list = [misc.cen2bound(this_loglam) for this_loglam in modloglam_list]
    modwave_list = [10.**this_loglam for this_loglam in modloglam_list]
    modwavebound_list = [10.**this_logbound for this_logbound in modlogbound_list]
    # Interpolate the spectrum-frame sigmas onto the model-frame grids:
    modsigma_list = [n.interp(modwave_list[k], wave_list[k], sigma_list[k]) for k in xrange(nspec)]
    # Compute the projection matrices:
    matrix_list = [misc.gaussproj(modwavebound_list[k], modsigma_list[k],
                                  wavebound_list[k]) for k in xrange(nspec)]
    # Return results:
    return matrix_list, idx_list, nsamp_list

class MultiProjector:
    """
    Class to take a list of spectro wavelength baselines and
    associated instrumental dispersion parameters and return
    an object that implements projection from uniform log10-lambda
    baseline model grid.

    This started as an object-wrapper to the function
      multi_projector
    See the documentation for that function for more information
    on the non-trivial internals of this class.
    The class has since evolved to a more expansive container
    for and interface to spectra and their associated vectors.
    
    Arguments:
      wavebound_list: List of 1D vectors each containing the
        pixel boundaries of the individual spectra.  Each
        vector is taken to be of length npix_j + 1, where
        npix_j is the number of pixels in the j'th spectrum
        Must be monotonically increasing or something will crash.
      sigma_list: List of instrumental Gaussian sigma dispersion
        parameter vectors.  Each vector to be of length npix_j
      flux_list: List of fluxes of spectra, in f-lambda units,
        with the per-lambda units matching those of the baseline
        specified by wavebound_list (but with npix_j rather than
        npix_j + 1 as the length of each vector).
      invvar_list: List of inverse variance vectors associated
        with flux_list.
      coeff0: log10-angstroms (vacuum, rest frame) of the zeroth
        pixel of the constant log10-lambda grid from which the
        projection matrices should broadcast to the individual
        spectra.
      coeff1: delta log10-angstroms per pixel of the constant
        log10-lambda grid from which the projection matrices
        should broadcast to the individual spectra.

    Written: bolton@utah@iac 2014junio
    """
    def __init__(self,
                 wavebound_list=None,
                 sigma_list=None,
                 flux_list=None,
                 invvar_list=None,
                 coeff0=None, coeff1=None,
                 npoly=3):
        """
        Constructor for the MultiProjector object.

        Arguments:
        wavebound_list: List of 1D vectors each containing the
          pixel boundaries of the individual spectra.  Each
          vector is taken to be of length npix_j + 1, where
          npix_j is the number of pixels in the j'th spectrum
          Must be monotonically increasing or something will crash.
        sigma_list: List of instrumental Gaussian sigma dispersion
          parameter vectors.  Each vector to be of length npix_j
        flux_list: List of fluxes of spectra, in f-lambda units,
          with the per-lambda units matching those of the baseline
          specified by wavebound_list (but with npix_j rather than
          npix_j + 1 as the length of each vector).
        invvar_list: List of inverse variance vectors associated
          with flux_list.
        coeff0: log10-angstroms (vacuum, rest frame) of the zeroth
          pixel of the constant log10-lambda grid from which the
          projection matrices should broadcast to the individual
          spectra.
        coeff1: delta log10-angstroms per pixel of the constant
          log10-lambda grid from which the projection matrices
          should broadcast to the individual spectra.
        npoly: polynomial background order for use in fitting,
          defaulting to 3 (quadratic).
        """
        self.nspec = len(wavebound_list)
        self.npix_list = [len(this_sigma) for this_sigma in sigma_list]
        self.coeff0 = coeff0
        self.coeff1 = coeff1
        self.wavebound_list = copy.deepcopy(wavebound_list)
        self.sigma_list = copy.deepcopy(sigma_list)
        self.flux_list = copy.deepcopy(flux_list)
        self.invvar_list = copy.deepcopy(invvar_list)
        self.wavecen_list = [0.5 * (this_bound[1:] + this_bound[:-1])
                             for this_bound in wavebound_list]
        self.big_data = n.hstack(self.flux_list)
        self.big_ivar = n.hstack(self.invvar_list)
        self.big_wave = n.hstack(self.wavecen_list)
        self.matrix_list, self.idx_list, self.nsamp_list = \
            multi_projector(wavebound_list, sigma_list, coeff0, coeff1)
        self.set_npoly(npoly)
        self.emvdisp = []
    def project_model_grid(self, model_grid, pixlag=0, coeff0=None):
        """
        Function to project a grid of constant-log10-lambda models onto
        the individual frames of multiple spectra, with pixel-redshift
        
        Arguments:
          model_grid: ndarray of models gridded in constant log10-Angstroms.
            Wavelength dimension must be final dimension.  Any number of
            leading dimensions is allowed.
          pixlag: pixel-redshift to apply when placing projection matrices
            within model loglam grids.  By convention, pixlag > 0 is redshift
            and pixlag < 0 is blueshift.
          coeff0: Override value if the model grid has a zero-pixel
            log10-Angstrom value other than that which is in self.coeff0.
            This will be converted to pixels and rounded to an integer value.
        """
        # Do we need to offset for a different coeff0?
        if coeff0 is None:
            ishift = 0
        else:
            # If argument coeff0 is greater than self.coeff0, then
            # we need to index our matrices into lower-numbered
            # indices within the model baseline.  If this corresponds
            # to a positive 'ishift' value as it does here, then it
            # corresponds to subtraction when building the slices
            # in the code immediately below.
            ishift = int(round((coeff0 - self.coeff0) / self.coeff1))
        # Build a list of slices within the model grid:
        slice_list = [slice(self.idx_list[k]-pixlag-ishift,
                            self.idx_list[k]+self.nsamp_list[k]-pixlag-ishift)
                      for k in xrange(self.nspec)]
        # How many pixels in the model grids?
        npix_model = model_grid.shape[-1]
        # Dimensionality of the model-grid space:
        dimshape_model = model_grid.shape[:-1]
        # Total number of models for looping:
        nmodels = model_grid.size // npix_model
        # Make a flattened view of the model grids for looping:
        model_flatgrid = model_grid.reshape((nmodels, npix_model))
        # Initialize output list, in flattened form:
        outgrid_list = [n.zeros((nmodels, this_npix), dtype=float)
                        for this_npix in self.npix_list]
        # Now loop over exposures and models:
        for j_spec in xrange(self.nspec):
            for i_mod in xrange(nmodels):
                outgrid_list[j_spec][i_mod] = self.matrix_list[j_spec] \
                  * model_flatgrid[i_mod,slice_list[j_spec]]
            # Resize the output grid to match the input model-space dimensions:
            outgrid_list[j_spec].resize(dimshape_model + (self.npix_list[j_spec],))
        return outgrid_list
    def make_emline_basis(self, z=0., vdisp=0.):
        """
        Method to generate a list of Gaussian emission-line basis functions
        at a particular redshift and velocity width in the observed frame
        of the individual exposures.
        """
        # Compute observed wavelength of emission lines:
        lambda_obs = (1. + z) * gal_emline_wave
        # Compute intrinsic velocity width of lines, in wavelength units
        sigma_line = lambda_obs * vdisp / c_kms
        # Interpolate for instrumental sigma values:
        lsf_list = [n.interp(lambda_obs, self.wavecen_list[k], self.sigma_list[k])
                    for k in xrange(self.nspec)]
        # Add intrinsic and instrumental in quadrature:
        linesigma_list = [n.sqrt(sigma_line**2 + this_lsf**2)
                          for this_lsf in lsf_list]
        # Generate projection matrices from amplitudes to pixels:
        return [n.asarray(misc.gaussbasis(self.wavebound_list[k], lambda_obs,
                                          linesigma_list[k]).T.todense())
                for k in xrange(self.nspec)]
    def single_poly_nonneg(self, npoly):
        """
        Method to generate a single global (model-space) observed-frame
        non-negative polynomial basis of order 'npoly' and project it through
        the projection matrices into the frames of the individual spectra.
        """
        idx_lo = min(self.idx_list)
        idx_hi = max(n.asarray(self.idx_list) + n.asarray(self.nsamp_list))
        npix_poly = idx_hi - idx_lo
        poly_base = n.arange(npix_poly) / float(npix_poly-1)
        poly_grid = n.zeros((2*int(round(npoly)), npix_poly), dtype=float)
        for ipoly in xrange(int(round(npoly))):
            poly_grid[2*ipoly] = poly_base**ipoly
            poly_grid[2*ipoly+1] = - poly_base**ipoly
        return self.project_model_grid(poly_grid, pixlag=idx_lo)
    def set_npoly(self, npoly):
        """
        Method to set the polynomial background order for use in fitting,
        and to precompute arrays that use it.
        """
        self.npoly = npoly
        self.poly_grid = self.single_poly_nonneg(npoly)
        self.big_poly = n.hstack(self.poly_grid)
    def set_models(self,
                   model_grid,
                   baselines=None,
                   n_linear_dims=0,
                   coeff0=None):
        """
        Method to associate redshift template models with the object.
        Arguments:
          model_grid: grid of models with constant dlog10wave/dpix equal
            to the value of 'coeff1' with which the MultiProjector object
            was created (otherwise nothing works right).  Dimensions are:
              n0 x n1 x ... x nJ x nWave,
            where the first dimensions index parameters of the models,
            and the last dimension indexes the (constant-log10-lambda)
            wavelength dimension.  Should be numpy ndarray.
          baselines: list of 1d vector ndarrays holding the parameter
            baselines corresponding to the dimensions of the model grid.
            This is most conveniently supplied from the output of
            read_ndArch.  This argument is optional, but you may have
            troubles down the line if you don't 
          n_linear_dims: The default assumption is that all model parameter
            dimensions are to be considered non-linear and to be given their
            own corresponding dimension in an eventual chi-squared grid.
            However, it is possible for some of the trailing dimensions to be
            treated as linear dimensions, in which case at each point in the
            non-linear grid, the data will be fit as a non-negative linear
            combination of all the corresponding model vectors across the
            linear dimensions.
            **NOTE** that any linear dimensions MUST come AFTER all the
            nonlinear dimensions in the ordering of parameter dimensions
            of the model grid
          coeff0: log10-Angstroms of zero pixel of the model grid,
            if different than value with which object was created.
            Supplying a value for this variable will change the coeff0
            attribute of the object.
        Note: we may eventually want to change this routine to just take
          an ndArch filename as its argument.  That might be simpler.
        Note: we probably want to put in some checking for legitimate
          values of n_linear_dims.
        """
        self.model_grid = model_grid.copy()
        if (baselines is not None):
            self.baselines = copy.deepcopy(baselines)
        self.n_linear_dims = n_linear_dims
        if (coeff0 is not None):
            self.coeff0 = coeff0
    def set_emvdisp(self, emline_vlist=None):
        """
        Method to set the list of (Gaussian) emission-line widths
        to consider as a non-linear parameter grid dimension when
        performing redshift model fits.  Should be a list or a
        1d ndarray of values in km/s for the line 'sigma' values.
        Call with no arguments to remove emission-line components.
        """
        if (emline_vlist is not None):
            self.emvdisp = emline_vlist
        else:
            self.emvdisp = []
    def grid_chisq(self, pixlags):
        """
        Method to compute chi-squared for the spectro data over a parameterized
        grid of models, including redshifting, nonnegative linear superpositions,
        and emission lines.

        Argument:
          pixlags: vector of integer pixel 'lags' (shifts) within the
            constant-log10-lambda grid to explore in order to implement
            the redshift dimension.  Positive pixlags are by convention taken
            to be redshifts.  A value of zero is rest-frame.
        """
        # Figure out what dimensionality we need for the chi-squared grid
        # in the initial working (flattened) form (including always a dimension
        # for the emission-line velocity widths):
        n_nonlin_dims = len(self.model_grid.shape) - self.n_linear_dims - 1
        nonlin_shape = self.model_grid.shape[:n_nonlin_dims]
        nonlin_len = n.prod(n.asarray(nonlin_shape, dtype=int))
        # Number of model pixels:
        npix_mod = self.model_grid.shape[-1]
        # Number of pixels in the linear dimension:
        linear_len = (self.model_grid.size // npix_mod) // nonlin_len
        # View of the model grid reshaped to what we need:
        model_grid_reshape = self.model_grid.reshape((nonlin_len, linear_len, npix_mod))
        # Sort out number of pixlags to consider:
        pixlags_local = n.asarray(pixlags).ravel()
        n_pixlag = len(n.asarray(pixlags_local))
        # Number of emission-line widths:
        n_vline = len(self.emvdisp)
        # Necessary size of emission-line width dimension
        # (have to have an indexing placeholder even if no emission lines)
        vline_len = n.maximum(n_vline, 1)
        self.chisq_grid = n.zeros((nonlin_len, vline_len, n_pixlag), dtype=float)
        # Now the loop over non-linear parameters,redshift, and emision-line parameters:
        
        pass


n_nonlin_dims = 1
nonlin_shape = MP.model_grid.shape[:n_nonlin_dims]
nonlin_len = n.prod(n.asarray(nonlin_shape, dtype=int))
# Number of model pixels:
npix_mod = MP.model_grid.shape[-1]
# Number of pixels in the linear dimension:
linear_len = (MP.model_grid.size // npix_mod) // nonlin_len
# View of the model grid reshaped to what we need:
model_grid_reshape = MP.model_grid.reshape((nonlin_len, linear_len, npix_mod))
model_grid_reshape.shape
