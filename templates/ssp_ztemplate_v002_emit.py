import numpy as n
import matplotlib as m
m.interactive(True)
from matplotlib import pyplot as p
from astropy.io import fits
#from astropy import wcs
import os
#import pixelsplines as pxs
from redmonster.datamgr import io
from redmonster.physics import pixelsplines as pxs
import copy
from redmonster.physics import misc

# ssp_ztemplate_v00.py
# Script to generate redshift templates at SDSS sampling
# from Charlie Conroy's theoretical SSPs.
# bolton@utah@iac 2014mayo
# original version bolton@utah@iac 2014mayo
# this version bolton@utah 2015agosto

# This version implements emission-line ratio variation
# based on BPT phenomenology, to work in tandem with v002_cont,
# which has emission-line dimension scaled back relative to
# previous version, since ELG/AGN now represented in
# template file generated by this script here.


# Set this:
# export SSP_DATA_DIR=/data/SSP

# First read in the templates:
sspf = os.getenv('SSP_DATA_DIR') + '/SSP_Padova_RRLIB_Kroupa_Z0.0190.fits'
ssp_data = fits.getdata(sspf, 1)
ssp_meta = fits.getdata(sspf, 2)
ssp_wave = ssp_data['LAMBDA'][0].copy()
ssp_flux = ssp_data['SPEC'][0].copy()
ssp_agegyr = ssp_meta['AGEGYR'].copy()
n_age, n_pix = ssp_flux.shape

# Need to sort out conversion from Lnu to Llambda..
# These come in Lsun per Hz.
# So, we need to first multiply by...
Lsun_in_cgs = 3.839e33
# which will get us to ergs per second per Hz.
# Then we need to convert from angstroms to cm
# for purposes of flux-unit conversion:
ang_per_cm = 1.e8
#ssp_wave_cm = ssp_wave / ang_per_cm
# We also need speed of light in cgs units:
c_cgs = 2.99792458e10
# So, the conversion vector is:
#(Lsun_in_cgs * c_cgs / (ssp_wave_cm**2)) * ang_per_cm
# where the last ang_per_cm puts it in per-angstrom.
# This is all equivalent to:
fluxconv = Lsun_in_cgs * c_cgs / (ssp_wave**2 * ang_per_cm)
# by cancelling one of the powers of ang_per_cm,
# since (again) ssp_wave is in Angstroms.

# the actual conversion:
ssp_flam = ssp_flux * fluxconv.reshape((1,-1))

# Exponent to divide out:
exp_div = 12
ssp_flam /= 10.**exp_div

# Get a subset of the templates:
izero = n.argmin(n.abs(n.log10(ssp_agegyr) - (-2.0)))
idx = 20 * n.arange(7) + izero
n.log10(ssp_agegyr[idx])
nsub_age = len(idx)

# Work out the pixel boundaries and widths
# (we go to log-lambda because the
# spacing is uniform in that):
ssp_loglam = n.log10(ssp_wave)
ssp_logbound = pxs.cen2bound(ssp_loglam)
ssp_wavebound = 10.**ssp_logbound
#ssp_dwave = ssp_wavebound[1:] - ssp_wavebound[:-1]
# Note that there is some slight unsmoothness in the
# width of the sampling intervals.  I think this is fine,
# but it will imply a slightly variable resolution
# implicit in the data as it currently stands if we dial
# it in straight from the pixel widths.  So instead, let's
# try setting it based on the average loglam spacing,
# since that is essentially uniform.
# p.plot(ssp_logbound[1:] - ssp_logbound[:-1], hold=False)
dloglam = n.mean(ssp_logbound[1:] - ssp_logbound[:-1])

# This will work:
#ssp_dwave = 10.**(ssp_loglam + 0.5 * dloglam) - \
#            10.**(ssp_loglam - 0.5 * dloglam)
#ssp_dwave = ssp_wave * (10**(dloglam/2.) - 10.**(-dloglam/2.))

# THIS is the best way to do it!!
ssp_dwave = dloglam * ssp_wave * n.log(10.)

# What is the resolution that we want to add in order
# to make the SDSS pixel width?
sdss_dloglam = 0.0001
sdss_dwave = sdss_dloglam * ssp_wave * n.log(10.)

# This constructs the blurring matrix to SDSS resolution:
sdss_blur = pxs.gauss_blur_matrix(ssp_wavebound, n.sqrt(sdss_dwave**2 - ssp_dwave**2))

# The baseline for log vdisp in km/s:
log_vmin = 2.1
log_vstep = 0.3
log_vnum = 2
log_vbase = log_vmin + log_vstep * n.arange(log_vnum)

# Compute the velocity-broadening matrices:
c_kms = 2.99792458e5
sigma_v_in_ang = ssp_wave.reshape((1,-1)) * (10.**log_vbase).reshape((-1,1)) / c_kms
vmatrix_list = [pxs.gauss_blur_matrix(ssp_wavebound, sigma_v_in_ang[i]) for i in xrange(log_vnum)]

# Initialize an array to hold the blurred SSPs before downsampling:
ssp_vblur = n.zeros((nsub_age, log_vnum, n_pix), dtype=float)

for i_age in xrange(nsub_age):
    print(i_age)
    this_flux = sdss_blur * ssp_flam[idx[i_age]]
    for j_logv in xrange(log_vnum):
        ssp_vblur[i_age,j_logv] = vmatrix_list[j_logv] * this_flux

#i = -1L
#
#i +=1
#p.plot(ssp_wave, ssp_vblur[i,0], hold=False)
#p.plot(ssp_wave, ssp_vblur[i,1], hold=True)
#p.plot(ssp_wave, ssp_vblur[i,2], hold=True)
#p.plot(ssp_wave, ssp_vblur[i,3], hold=True)
#p.title(str(n.log10(ssp_agegyr[idx[i]])))

# After verifying edge-effect range, wavelength range
# for rebinned SDSS version to be bounded by:
wave_sdss_lo = 1525.
wave_sdss_hi = 10850.
coeff1 = sdss_dloglam
coeff0 = coeff1 * n.floor(n.log10(wave_sdss_lo) / coeff1)
naxis1 = int(n.ceil(1. + (n.log10(wave_sdss_hi) - coeff0) / coeff1))

loglam_sdss = coeff0 + coeff1 * n.arange(naxis1)
logbound_sdss = pxs.cen2bound(loglam_sdss)
wavebound_sdss = 10.**logbound_sdss

# Initialize array for rebinned blurred SSPs:
ssp_sdssbin = n.zeros((nsub_age, log_vnum, naxis1), dtype=float)

# Do the rebinning:
for i_age in xrange(nsub_age):
    print(i_age)
    for j_logv in xrange(log_vnum):
        pxspline = pxs.PixelSpline(ssp_wavebound, ssp_vblur[i_age,j_logv])
        ssp_sdssbin[i_age,j_logv] = pxspline.resample(wavebound_sdss)

#i = -1L

#i +=1
#p.plot(10.**loglam_sdss, ssp_sdssbin[i,0], drawstyle='steps-mid', hold=False)
#p.plot(10.**loglam_sdss, ssp_sdssbin[i,1], drawstyle='steps-mid', hold=True)
#p.plot(10.**loglam_sdss, ssp_sdssbin[i,2], drawstyle='steps-mid', hold=True)
#p.plot(10.**loglam_sdss, ssp_sdssbin[i,3], drawstyle='steps-mid', hold=True)
#p.title(str(n.log10(ssp_agegyr[idx[i]])))


# Now to get the emission-line fluxes:
emfile = 'elg_agn_linedata.fits'
lratio = fits.getdata(emfile,0)
lsigma = fits.getdata(emfile,1)
ltable = fits.getdata(emfile,2)

# Need to work out the (sigma) line width of each
# line in Angstroms:
# Instrumental line width:
lsigma_instrument = ltable['lambda'] * coeff1 * n.log(10.)

# Number of unique emission-line ratios:
n_ratios = lratio.shape[0]

# Loop over unique line-ratio combinations to populate template array:
n_line = len(ltable['lambda'])
sdss_line_array = n.zeros((n_line, naxis1), dtype=float)
emline_templates = n.zeros((n_ratios, naxis1), dtype=float)
for i in xrange(n_ratios):
    # Velocity width, in Angstroms:
    lsigma_velocity = ltable['lambda'] * lsigma[i] / c_kms
    # Add in quadrature with instrumental value:
    lsigma_angstroms = n.sqrt(lsigma_instrument**2 + lsigma_velocity**2)
    # Build array holding normalized individual line profiles:
    for j in xrange(n_line):
        sdss_line_array[j] = misc.gaussflux(wavebound_sdss, ltable['lambda'][j],
                                            lsigma_angstroms[j])
    # Generate template spectrumfor this set of line ratios:
    emline_templates[i] = n.dot(lratio[i], sdss_line_array)

# Test normalization (for last array of lines):
wave_sdss = 10.**loglam_sdss
deltawave_sdss = wavebound_sdss[1:] - wavebound_sdss[:-1]

n.dot(sdss_line_array, deltawave_sdss)
# Checks out as a bunch of 1's

# QA plotting:
# holdvec = n.ones(n_ratios)
# holdvec[0] = 0
# for i in xrange(n_ratios):
#     p.plot(wave_sdss, emline_templates[i], drawstyle='steps-mid', hold=holdvec[i])

# Average spectrum over velocity dispersions for each age:
sdss_meanspec = ssp_sdssbin.mean(axis=1)
# Pick a bandwidth over which to average the continuum at Halpha
bandhw = 100.
wtest = (wave_sdss > (ltable['lambda'][8] - bandhw)) * \
        (wave_sdss < (ltable['lambda'][8] + bandhw))

cont_halpha = n.asarray([n.sum(sdss_meanspec[i] * wtest * deltawave_sdss) /
                         n.sum(deltawave_sdss * wtest) for i in xrange(nsub_age)])

# Let's try the following range of Halpha equivalent widths:
ew_ha = n.asarray([4., 8., 16., 32., 64., 128.])
n_ew = len(ew_ha)

# Broadcast-fu to add the line spectra and expand the grid:
full_sdssbin = cont_halpha.reshape((-1,1,1,1,1)) * \
               ew_ha.reshape((1,1,-1,1,1)) * \
               emline_templates.reshape((1,1,1,n_ratios,-1)) + \
               ssp_sdssbin.reshape((nsub_age,log_vnum,1,1,naxis1))


# Work out the appropriate baseline for the "BPT" parameter:
bpt_base = n.log10(lratio[:,9])

baselines = [n.log10(ssp_agegyr[idx]), log_vbase, ew_ha, bpt_base]

this_class = 'ssp_galaxy_emit'
this_version = 'v002'

infodict = {'par_names': n.asarray(['log10-age', 'log10-vdisp', 'EW_Halpha', 'log10_NII_Ha']),
            'par_units': n.asarray(['log10-Gyr', 'log10-km/s', 'rest-frame Angstroms', 'log-ratio']),
            'par_axistype': n.asarray(['regular', 'regular', 'irregular', 'irregular']),
            'coeff0': coeff0, 'coeff1': coeff1,
            'fluxunit': '10^'+str(exp_div)+' erg/s/Ang/M_sun_init',
            'filename': 'ndArch-'+this_class+'-'+this_version+'.fits'}

io.write_ndArch(n.float32(full_sdssbin), baselines, infodict)

#junk, bjunk, ijunk = io.read_ndArch(infodict['filename'])

