import libcurvedsky

def cnfilter_freq(n,mn,nside,lmax,cl,bl,iNcov,maps,chn=1,lmaxs=[0],nsides=[0],itns=[1],eps=[1e-6],filter='',verbose=False,ro=50,stat='',inl=0):
  """
 Combining multiple frequency maps optimally. 
 The filtering would work if the noise variance is not significantly varied with scale (multipole). 

 Args:
    :n (*int*): Number of maps, i.e., temperature only (n=1), polarization only (n=2) or both (n=3)
    :mn (*int*): Number of frequencies
    :nside (*int*): Nside of input map
    :lmax (*int*): Maximum multipole of the input cl
    :cl[*n,l*] (*double*): Theory signal power spectrum, with bounds (0:n-1,0:lmax)
    :bl[*mn,l*] (*double*): Beam spectrum, with bounds (0:mn-1,0:lmax)
    :iNcov[*n,mn,pix*] (*double*): Inverse of the noise variance at each pixel, with bounds (0:n-1,0:mn-1,0:npix-1)
    :maps[*n,mn,pix*] (*double*): Input T, Q, U maps, with bouds (0:n-1,0:mn-1,0:npix-1)

 Args(optional):
    :chn (*int*): number of grids for preconsitioner (chn=1 for diagonal preconditioner, default)
    :lmaxs[*chain*] (*int*): Maximum multipole(s) at each preconditioning and lmaxs[*0*] is the input maximum multipole of cl
    :nsides[*chain*] (*int*): Nside(s) of preconditoner and nsides[*0*] should be consistent with the input map's nside.
    :eps[*chain*] (*double*): Numerical parameter to finish the iteration if ave(\|Ax-b\|)<eps, default to 1e-6
    :itns[*chain*] (*int*): Number of interation(s)
    :filter (*str*): C-inverse ('') or Wiener filter (W), default to C-inverse.
    :inl[*n,mn,l*] (*double*): inverse noise spectrum for non white noise case.
    :verbose (*bool*): Output messages, default to False
    :stat (*str*): Realtime status filename, default to no output file

 Returns:
    :xlm[*n,l,m*] (*dcmplx*): C-inverse / Wiener filtered multipoles, with bounds (0:n-1,0:lmax,0:lmax)

  Usage:
    :xlm = curvedsky.cninv.cnfilter_freq(n,mn,nside,lmax,cl,bl,iNcov,maps,chn,lmaxs,nsides,itns,eps,filter,inl,verbose,ro,stat):
  """
  npix = 12*nside**2
  return libcurvedsky.cninv.cnfilter_freq(n,mn,npix,lmax,cl,bl,iNcov,maps,chn,lmaxs,nsides,itns,eps,filter,inl,verbose,ro,stat)

def cnfilter_freq_nside(n,mn0,mn1,nside0,nside1,lmax,cl,bl0,bl1,iNcov0,iNcov1,maps0,maps1,chn=1,lmaxs=[0],nsides0=[0],nsides1=[0],itns=[1],eps=[1e-6],filter='',verbose=False,reducmn=0,ro=50,stat='',inl=0):
  """
 Same as cnfilter_freq but for the maps with two different Nsides. 

 Args:
    :n (*int*): Number of maps, i.e., temperature only (n=1), polarization only (n=2) or both (n=3)
    :mn0/1 (*int*): Number of frequencies
    :nside0/1 (*int*): Nsides of input maps
    :lmax (*int*): Maximum multipole of the input cl
    :cl[*n,l*] (*double*): Theory signal power spectrum, with bounds (0:n-1,0:lmax)
    :bl0/1[*mn,l*] (*double*): Beam function, with bounds (0:n-1,0:lmax)
    :iNcov0/1[*n,mn,pix*] (*double*): Inverse of the noise variance at each pixel, with bounds (0:n-1,0:npix-1)
    :maps0/1[*n,mn,pix*] (*double*): Input T, Q, U maps, with bouds (0:n-1,0:npix-1)

 Args(optional):
    :chn (*int*): number of grids for preconsitioner (chn=1 for diagonal preconditioner, default)
    :lmaxs[*chain*] (*int*): Maximum multipole(s) at each preconditioning and lmaxs[*0*] is the input maximum multipole of cl
    :nsides0/1[*chain*] (*int*): Nside(s) of preconditoner and nsides[*0*] should be consistent with the input map's nside.
    :eps[*chain*] (*double*): Numerical parameter to finish the iteration if ave(\|Ax-b\|)<eps, default to 1e-6
    :itns[*chain*] (*int*): Number of interation(s)
    :filter (*str*): C-inverse ('') or Wiener filter (W), default to C-inverse.
    :verbose (*bool*): Output messages
    :reducmn (*int*): Reducing number of maps per chain (1,2) or not (0, default). If 1, the maps are combined for the same nside inside the multigrid chain. If 2, in addition to the procedure of 1, the each nside maprs are further combined into a single map inside the second chain (chain>=3).
    :stat (*str*): Realtime status filename

 Returns:
    :xlm[*n,l,m*] (*dcmplx*): C-inverse / Wiener filtered multipoles, with bounds (0:n-1,0:lmax,0:lmax)

      mgc%cv(1,mi)%nij = iNcov0(:,mi,:)maps0(:,mi,:)
      mgc%cv(1,mi)%nij = iNcov1(:,mi-mn0,:)maps1(:,mi-mn0,:)
  Usage:
    :xlm = curvedsky.cninv.cnfilter_freq_nside(n,mn0,mn1,nside0,nside1,lmax,cl,bl0,bl1,iNcov0,iNcov1,maps0,maps1,chn,lmaxs,nsides0,nsides1,itns,eps,filter,inl,verbose,reducmn,ro,stat):
  """
  npix0 = 12*nside0**2
  npix1 = 12*nside1**2
  return libcurvedsky.cninv.cnfilter_freq_nside(n,mn0,mn1,npix0,npix1,lmax,cl,bl0,bl1,iNcov0,iNcov1,maps0,maps1,chn,lmaxs,nsides0,nsides1,itns,eps,filter,inl,verbose,reducmn,ro,stat)

