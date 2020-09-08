
import configparser
import sys
import os
import numpy as np
import pickle
import tqdm

# cmblensplus/wrap/
import basic
import curvedsky

# local
import misctools


# Define quad estimator names
class quad_fname:

    def __init__(self,pquad,qest,root,ids,cmbtag):

        # qtype is the type of mode coupling, such as lens, rot, etc
        qalm = root + pquad.qtype + '/alm/'
        qrdn = root + pquad.qtype + '/rdn0/'
        qmlm = root + pquad.qtype + '/mean/'
        qaps = root + pquad.qtype + '/aps/'

        otag = pquad.otag
        qtag = qest+'_'+cmbtag+pquad.ltag+pquad.qtagext

        # normalization and tau transfer function
        self.al   = qaps+'Al_'+qtag+'.dat'
        self.wl   = qaps+'Wl_'+qtag+'.dat'

        # N0 bias
        self.n0bs = qaps+'n0_'+qtag+'_n'+str(pquad.n0sim).zfill(3)+'.dat'

        # mean field
        self.ml   = [qmlm+'cl_'+qtag+'_'+x+'.dat' for x in ids]
        self.mfb  = [qmlm+'mlm_'+qtag+'_'+x+'.pkl' for x in ids]
        self.mfcl = qmlm+'mfcl_'+qtag+'_n'+str(pquad.mfsim).zfill(3)+'.dat'
        self.mf   = qmlm+'mfalm_'+qtag+'_n'+str(pquad.mfsim).zfill(3)+'.pkl'

        # reconstructed spectra
        self.mcls = qaps+'cl_'+qtag+'.dat'
        self.ocls = qaps+'cl_'+ids[0]+'_'+qtag+'.dat'
        self.cl   = [qaps+'rlz/cl_'+qtag+'_'+x+'.dat' for x in ids]

        # reconstructed alm and RDN0
        self.alm  = [qalm+'alm_'+qtag+'_'+x+'.pkl' for x in ids]
        self.rdn0 = [qrdn+'rdn0_'+qtag+'_n'+str(pquad.rdsim).zfill(3)+'_'+x+'.dat' for x in ids]

        # diagonal RDN0
        self.ddn0 = [qrdn+'ddn0_'+qtag+'_'+x+'.dat' for x in ids]

        # reconstruction noise variance map
        self.nkmap = qalm+'nkmap_'+qtag+'.pkl'

        # additional alms
        self.walm = [qalm+'walm_'+qtag+'_'+x+'.pkl' for x in ids]


class quad:

    def __init__(self, rlz=[], lcl=None, ocl=None, ifl=None, falm='',
                 olmax=2048, rlmin=500, rlmax=3000, nside=2048,
                 n0min=1, n0max=50, rdmin=1, rdmax=100, mfmin=1, mfmax=100,
                 qDO=None, qMV=None, qlist=None, qtype='', wn=None, bhe=None, rd4sim=False, 
                 overwrite=False, verbose=True
                ):

        #//// get parameters ////#
        conf = misctools.load_config('QUADREC')

        # define parameters for quadratic estimator computations
        self.qtype = conf.get('qtype','lens')
        if qtype!='':  self.qtype = qtype

        self.nside  = conf.getint('nside',nside)
        self.rlmin  = conf.getint('rlmin',rlmin)
        self.rlmax  = conf.getint('rlmax',rlmax)

        if 3*self.nside < self.rlmax:  print('Warning: nside^rec would be too small for reconstruction')

        self.olmin  = conf.getint('olmin',1)
        self.olmax  = conf.getint('olmax',olmax)
        self.bn     = conf.getint('bn',30) 
        self.binspc = conf.get('binspc','')

        # iteration
        self.rlz    = rlz
        
        # start, stop rlz of N0 bias
        self.n0min  = conf.getint('n0min',n0min)
        self.n0max  = conf.getint('n0max',n0max)
        self.n0sim  = self.n0max - self.n0min + 1
        self.n0rlz  = np.linspace(self.n0min,self.n0max,self.n0sim,dtype=np.int)

        # start, stop rlz of RDN0 bias
        self.rdmin  = conf.getint('rdmin',rdmin)
        self.rdmax  = conf.getint('rdmax',rdmax)
        self.rdsim  = self.rdmax - self.rdmin + 1
        self.rd4sim = conf.getboolean('rd4sim',rd4sim)  # whether RD calculation for sim
        # start, stop rlz of mean-field
        self.mfmin  = conf.getint('mfmin',mfmin)
        self.mfmax  = conf.getint('mfmax',mfmax)
        self.mfsim  = self.mfmax - self.mfmin + 1

        # external tag
        self.qtagext = conf.get('qtagext','')

        self.oL     = [self.olmin,self.olmax]

        # rlz
        self.mfrlz = np.linspace(self.mfmin,self.mfmax,self.mfsim,dtype=np.int)

        # Cl for filter, obs Cl and alm files
        self.ifl = ifl
        if lcl is not None:  self.lcl  = lcl[:,:self.rlmax+1]
        if ocl is not None:  self.ocl  = ocl[:,:self.rlmax+1]
        if ifl is not None:  self.ifl  = ifl[:,:self.rlmax+1]
        self.falm = falm

        #definition of T+P
        if qDO is None:
            self.qDO = [True,True,True,False,False,False]
        if qMV is None:
            self.qMV = ['TT','TE','EE']

        #definition of qlist
        if qlist is None:
            self.qlist = ['TT','TE','EE','TB','EB','MV']
            if self.qtype=='rot':
                self.qlist = ['EB']
        else:
            self.qlist = qlist.copy()

        # window normalization correction
        if wn is None:
            self.wn = np.ones(5)
        else:
            self.wn = wn

        #cinv diag filter
        self.Fl = { m: np.zeros(self.rlmax+1) for m in ['T','E','B'] }

        #multipole bins
        self.l = np.linspace(0,self.olmax,self.olmax+1)
        self.bp, self.bc = basic.aps.binning(self.bn,self.oL,spc=self.binspc)

        #kappa
        self.kL = self.l*(self.l+1.)*.5

        #filename tags
        self.ltag = '_l'+str(self.rlmin)+'-'+str(self.rlmax)
        self.otag = '_oL'+str(self.olmin)+'-'+str(self.olmax)+'_b'+str(self.bn)+self.binspc

        # cmb alm mtype
        self.mtype = []
        for q in self.qlist:
            if q not in ['TT','TE','EE','TB','EB','MV']:
                sys.exit('invalid quadratic combination is specified')
            if q == 'MV': continue
            if not q[0] in self.mtype: self.mtype.append(q[0])
            if not q[1] in self.mtype: self.mtype.append(q[1])

        #//// Bias Herdened Estimators ////
        # bhe tyoes
        if bhe is None:
            self.bhe_do   = False
            self.bhe_list = []
        else:
            self.bhe_do   = True
            self.bhe_list = bhe
            if not isinstance(bhe,list):
                sys.exit('bhe should be a list')
        
        if self.qtype in self.bhe_list:
            sys.exit('qtype is included in bhe to be deprojected, please remove')

        if bhe is None:
            self.bhe_tag = ''
        else:
            self.bhe_tag = '_'+'-'.join(['bh']+self.bhe_list)

        #//// Misc ////#
        self.overwrite = overwrite
        self.verbose = verbose
        

    def fname(self,root,ids,cmbtag):  #setup filename

        self.f = {}
        for q in self.qlist:
            self.f[q] = quad_fname(self,q,root,ids,cmbtag+self.bhe_tag)


    def cinvfilter(self,mids={'T':0,'E':1,'B':2}):

        if self.ifl is None:
            for m in ['T','E','B']:
                self.Fl[m][self.rlmin:self.rlmax+1] = 1.
        else:
            ocl = self.ifl.copy()
            for l in range(self.rlmin,self.rlmax+1):
                for m in self.mtype:
                    i = mids[m]
                    self.Fl[m][l] = 1./ocl[i,l]
                    if ocl[i,l] <=0.:  
                        sys.exit(m+' inverse-filter is zero: ocl='+str(ocl[i,l])+' at l='+str(l))


    # compute normalization
    def al(self,ocls=None,output=True,gtype='k'):
        '''
        Return normalization of the quadratic estimators
        '''

        ocl = self.ocl
        lcl = self.lcl
        if ocls is not None:  ocl = ocls

        Lmax  = self.olmax
        rlmin = self.rlmin
        rlmax = self.rlmax
        oL    = np.linspace(0,Lmax,Lmax+1)

        self.Ags, self.Acs = {}, {}
        self.bhe_c = {}
        
        for q in self.qlist:

            if output and misctools.check_path(self.f[q].al,overwrite=self.overwrite,verbose=self.verbose): continue

            Al, At, As = 0., 0., 0. # for BHE
            
            if self.qtype=='lens' or 'lens' in self.bhe_list:
                if q=='TT': Ag, Ac = curvedsky.norm_lens.qtt(Lmax,rlmin,rlmax,lcl[0,:],ocl[0,:],gtype=gtype)
                if q=='TE': Ag, Ac = curvedsky.norm_lens.qte(Lmax,rlmin,rlmax,lcl[3,:],ocl[0,:],ocl[1,:],gtype=gtype)
                if q=='EE': Ag, Ac = curvedsky.norm_lens.qee(Lmax,rlmin,rlmax,lcl[1,:],ocl[1,:],gtype=gtype)
                if q=='TB': Ag, Ac = curvedsky.norm_lens.qtb(Lmax,rlmin,rlmax,lcl[3,:],ocl[0,:],ocl[2,:],gtype=gtype)
                if q=='EB': Ag, Ac = curvedsky.norm_lens.qeb(Lmax,rlmin,rlmax,lcl[1,:],ocl[1,:],ocl[2,:],gtype=gtype)
                if q=='MV':
                    ag, ac, Wg, Wc = curvedsky.norm_lens.qall(self.qDO,Lmax,rlmin,rlmax,lcl,ocl,gtype=gtype)
                    Ag, Ac = ag[5,:], ac[5,:]
                Al = Ag.copy() # for BHE

            if self.qtype=='rot':
                if q=='TB': Ag = curvedsky.norm_rot.qtb(Lmax,rlmin,rlmax,lcl[3,:],ocl[0,:],ocl[2,:])
                if q=='EB': Ag = curvedsky.norm_rot.qeb(Lmax,rlmin,rlmax,lcl[1,:],ocl[1,:],ocl[2,:])
                Ac = Ag*.0

            if self.qtype=='tau' or 'tau' in self.bhe_list:
                if q=='TT': Ag = curvedsky.norm_tau.qtt(Lmax,rlmin,rlmax,lcl[0,:],ocl[0,:])
                if q=='EB': Ag = curvedsky.norm_tau.qeb(Lmax,rlmin,rlmax,lcl[1,:],ocl[1,:],ocl[2,:])
                Ac = Ag*.0
                At = Ag.copy() # for BHE

            if self.qtype=='src' or 'src' in self.bhe_list:
                if q=='TT': Ag = curvedsky.norm_src.qtt(Lmax,rlmin,rlmax,ocl[0,:])
                Ac = Ag*.0
                As = Ag.copy() # for BHE
                    
            #//// Bias-hardened estimator (cross response) ////#
            # Currently, only TT is supported
            Rlt, Rls, Rts = 0., 0., 0.
            
            if self.qtype == 'lens':
                if q == 'TT':
                    if 'tau' in self.bhe_list:
                        Rlt = curvedsky.norm_lens.ttt(Lmax,rlmin,rlmax,lcl[0,:],ocl[0,:],gtype=gtype)
                    if 'src' in self.bhe_list:
                        Rls = curvedsky.norm_lens.stt(Lmax,rlmin,rlmax,lcl[0,:],ocl[0,:],gtype=gtype)
                    if 'src' in self.bhe_list and 'tau' in self.bhe_list:  
                        Rts = curvedsky.norm_tau.stt(Lmax,rlmin,rlmax,lcl[0,:],ocl[0,:])

            if self.qtype == 'tau':
                if q == 'TT':
                    if 'lens' in self.bhe_list:
                        Rlt = curvedsky.norm_lens.ttt(Lmax,rlmin,rlmax,lcl[0,:],ocl[0,:],gtype=gtype)
                    if 'src' in self.bhe_list and 'lens' in self.bhe_list:  
                        Rls = curvedsky.norm_lens.stt(Lmax,rlmin,rlmax,lcl[0,:],ocl[0,:],gtype=gtype)
                    if 'src' in self.bhe_list:
                        Rts = curvedsky.norm_tau.stt(Lmax,rlmin,rlmax,lcl[0,:],ocl[0,:])

            # Denominator
            DetR = 1 - Al*As*Rls**2 - Al*At*Rlt**2 - At*As*Rts**2 + 2.*Al*At*As*Rlt*Rls*Rts

            # Corrected normalization (to be multiplied to the unnormalized estimators)
            self.bhe_c[q] = {}

            if self.qtype == 'lens' and self.bhe_do:
                self.bhe_c[q]['lens']  = ( 1. - At*As*Rts**2 ) / DetR * Al
                self.bhe_c[q]['tau'] = ( Rls*As*Rts - Rlt ) / DetR * At * Al
                self.bhe_c[q]['src']  = ( Rlt*At*Rts - Rls ) / DetR * As * Al
                Ag = self.bhe_c[q]['lens']

            if self.qtype == 'tau' and self.bhe_do:
                self.bhe_c[q]['tau']  = ( 1. - Al*As*Rls**2 ) / DetR * At
                self.bhe_c[q]['lens'] = ( Rts*As*Rls - Rlt ) / DetR * Al * At
                self.bhe_c[q]['src']  = ( Rlt*Al*Rls - Rts ) / DetR * As * At
                Ag = self.bhe_c[q]['tau']
                Ac = Ag*.0


            #//// save ////#
            if output:
                np.savetxt(self.f[q].al,np.array((oL,Ag,Ac)).T)
                if q=='MV' and self.qtype=='lens': 
                    for qi, qq in enumerate(['TT','TE','EE','TB','EB']): np.savetxt(self.f[qq].wl,np.array((oL,Wg[qi,:],Wc[qi,:])).T)

            # store
            self.Ags[q] = Ag
            self.Acs[q] = Ac
            if q=='MV':
                self.Wg = Wg
                self.Wc = Wc


    def loadnorm(self):

        Ag, Ac, Wg, Wc = {}, {}, {}, {}

        # load normalization
        for q in self.qlist:
            Ag[q], Ac[q] = np.loadtxt(self.f[q].al,unpack=True,usecols=(1,2))

        # load optimal weights
        if 'MV' in self.qlist and self.qtype=='lens':
            for qi, qq in enumerate(['TT','TE','EE','TB','EB']):  Wg[qq], Wc[qq] = np.loadtxt(self.f[qq].wl,unpack=True,usecols=(1,2))

        return Ag, Ac, Wg, Wc


    def qrec(self,qout=None,gtype='k'):
        '''
        Return quadratic estimators
        '''

        Lmax  = self.olmax
        rlmin = self.rlmin
        rlmax = self.rlmax
        nside = self.nside
        lcl   = self.lcl

        if qout == None:  qout = self

        # load normalization and weights
        Ag, Ac, Wg, Wc = self.loadnorm()
        
        # check BHE responses
        if self.bhe_do:
            if not hasattr(self,'bhe_c') or not self.bhe_c:
                self.al(output=False)

        # loop for realizations
        if len(self.rlz) <= 0: 
            print('nothing to do for qrec')

        for i in tqdm.tqdm(self.rlz,ncols=100,desc='reconstruction:'):
            
            gmv, cmv = 0., 0.

            # check file exits
            qlist = []
            for q in self.qlist:
                if misctools.check_path(qout.f[q].alm[i],overwrite=self.overwrite,verbose=self.verbose): continue
                qlist.append(q)
            if qlist==[]: continue

            # load cmb alms
            alm = { cmb: self.Fl[cmb][:,None] * pickle.load(open(self.falm[cmb][i],"rb"))[:rlmax+1,:rlmax+1] for cmb in self.mtype }

            for q in tqdm.tqdm(qlist,ncols=100,desc='each quad-comb:',leave=False):

                llm, tlm, slm = 0., 0., 0.
                
                if self.qtype=='lens' or 'lens' in self.bhe_list:
                    if q=='TT':  glm, clm = curvedsky.rec_lens.qtt(Lmax,rlmin,rlmax,lcl[0,:],alm['T'],alm['T'],gtype=gtype,nside_t=nside)
                    if q=='TE':  glm, clm = curvedsky.rec_lens.qte(Lmax,rlmin,rlmax,lcl[3,:],alm['T'],alm['E'],gtype=gtype,nside_t=nside)
                    if q=='TB':  glm, clm = curvedsky.rec_lens.qtb(Lmax,rlmin,rlmax,lcl[3,:],alm['T'],alm['B'],gtype=gtype,nside_t=nside)
                    if q=='EE':  glm, clm = curvedsky.rec_lens.qee(Lmax,rlmin,rlmax,lcl[1,:],alm['E'],alm['E'],gtype=gtype,nside_t=nside)
                    if q=='EB':  glm, clm = curvedsky.rec_lens.qeb(Lmax,rlmin,rlmax,lcl[1,:],alm['E'],alm['B'],gtype=gtype,nside_t=nside)
                    if q=='MV':  glm, clm = gmv.copy(), cmv.copy()
                    llm = glm.copy()

                if self.qtype=='rot':
                    if q=='TB':  glm = curvedsky.rec_rot.qtb(Lmax,rlmin,rlmax,lcl[3,:],alm['T'],alm['B'],nside_t=nside)
                    if q=='EB':  glm = curvedsky.rec_rot.qeb(Lmax,rlmin,rlmax,lcl[1,:],alm['E'],alm['B'],nside_t=nside)
                    clm = glm*0.

                if self.qtype=='tau' or 'tau' in self.bhe_list:
                    if q=='TT':  glm = curvedsky.rec_tau.qtt(Lmax,rlmin,rlmax,lcl[0,:],alm['T'],alm['T'],nside_t=nside)
                    if q=='EB':  glm = curvedsky.rec_tau.qeb(Lmax,rlmin,rlmax,lcl[1,:],alm['E'],alm['B'],nside_t=nside)
                    clm = glm*0.
                    tlm = glm.copy()

                if self.qtype=='src' or 'src' in self.bhe_list:
                    if q=='TT':  glm = curvedsky.rec_src.qtt(Lmax,rlmin,rlmax,alm['T'],alm['T'],nside_t=nside)
                    clm = glm*0.
                    slm = glm.copy()

                # normalization correction
                glm *= Ag[q][:,None]
                clm *= Ac[q][:,None]                

                # Bias hardened estimator
                if self.bhe_do:
                    glm = self.bhe_c[q]['tau'][:,None]*tlm + self.bhe_c[q]['lens'][:,None]*llm + self.bhe_c[q]['src'][:,None]*slm
                
                # save
                pickle.dump((glm,clm),open(qout.f[q].alm[i],"wb"),protocol=pickle.HIGHEST_PROTOCOL)

                # MV
                if q in self.qMV and 'MV' in self.qlist:
                    gmv += Wg[q][:,None]*glm
                    cmv += Wc[q][:,None]*clm


    def n0(self):
        '''
        The N0 bias calculation
        '''

        for q in self.qlist:
            if misctools.check_path(self.f[q].n0bs,overwrite=self.overwrite,verbose=self.verbose): return

        # load normalization and weights
        Ag, Ac, Wg, Wc = self.loadnorm()

        # check BHE responses
        if self.bhe_do:
            if not hasattr(self,'bhe_c') or not self.bhe_c:
                self.al(output=False)

        Lmax  = self.olmax
        qlist = self.qlist

        # power spectrum
        cl = {q: np.zeros((2,Lmax+1)) for q in qlist}

        # loop for realizations
        for i in tqdm.tqdm(self.n0rlz,ncols=100,desc='N0 bias:'):

            id0, id1 = 2*i-1, 2*i
            gmv, cmv = 0., 0.

            alm0 = { m: self.Fl[m][:,None]*pickle.load(open(self.falm[m][id0],"rb"))[:self.rlmax+1,:self.rlmax+1] for m in self.mtype }
            alm1 = { m: self.Fl[m][:,None]*pickle.load(open(self.falm[m][id1],"rb"))[:self.rlmax+1,:self.rlmax+1] for m in self.mtype }

            for q in tqdm.tqdm(qlist,ncols=100,desc='each quad-comb:',leave=False):

                if q == 'MV':
                    glm, clm = gmv.copy(), cmv.copy()
                else:
                    X, Y = q[0], q[1]
                    glm, clm = self.qXY(q,Lmax,alm0[X],alm1[X],alm0[Y],alm1[Y])

                if not self.bhe_do:
                    glm *= Ag[q][:,None]
                clm *= Ac[q][:,None]

                cl[q][0,:] += curvedsky.utils.alm2cl(Lmax,glm)/(2*self.wn[4]*self.n0sim)
                cl[q][1,:] += curvedsky.utils.alm2cl(Lmax,clm)/(2*self.wn[4]*self.n0sim)

                # MV
                if q in self.qMV and 'MV' in qlist:
                    gmv += Wg[q][:,None]*glm
                    cmv += Wc[q][:,None]*clm

        for q in qlist:
            oL = np.linspace(0,Lmax,Lmax+1)
            np.savetxt(self.f[q].n0bs,np.concatenate((oL[None,:],cl[q])).T)


    def diagrdn0(self,ocl,frcl):
        '''
        ocl = observed data cl
        frcl = filenames for sim cl for each rlz which mimics data cl
        '''
        
        oL = np.linspace(0,self.olmax,self.olmax+1)
        Ag, Ac, Wg, Wc = quad.loadnorm(self)

        for i in tqdm.tqdm(self.rlz,ncols=100,desc='Diag-RDN0:'):

            rcl = np.loadtxt(frcl[i],unpack=True,usecols=(1,2,3,4))  # cmb aps for ith realization
            rcl[np.where(rcl==0)] = 1e30 # a large number

            # data x data
            cl = ocl**2/rcl
            Ags0, Acs0 = self.al(ocls=cl,output=False)

            # (data-sim) x (data-sim)
            cl = ocl**2/(ocl-rcl)
            Ags1, Acs1 = self.al(ocls=cl,output=False)

            for q in self.qlist:

                Ags0[q][np.where(Ags0[q]==0)] = 1e30
                Ags1[q][np.where(Ags1[q]==0)] = 1e30
                Acs0[q][np.where(Acs0[q]==0)] = 1e30
                Acs1[q][np.where(Acs1[q]==0)] = 1e30

                n0g = Ag[q]**2*(1./Ags0[q]-1./Ags1[q])
                n0c = Ac[q]**2*(1./Acs0[q]-1./Acs1[q])
                
                np.savetxt(self.f[q].drdn0[i],np.array((oL,n0g,n0c)).T)


    def rdn0(self,qout=None,falms=None):
        '''
        The sim-data-mixed term of the RDN0 bias calculation
        '''

        # load normalization and weights
        Ag, Ac, Wg, Wc = self.loadnorm()

        # check BHE responses
        if self.bhe_do:
            if not hasattr(self,'bhe_c') or not self.bhe_c:
                self.al(output=False)

        falm  = self.falm
        Lmax  = self.olmax
        qlist = self.qlist

        if falms is None: falms = self.falm
        if qout  is None:  qout = self

        # load N0
        N0 = { q: np.loadtxt(self.f[q].n0bs,unpack=True,usecols=(1,2)) for q in qlist }

        # compute RDN0
        for i in tqdm.tqdm(self.rlz,ncols=100,desc='RDN0:'):

            # skip RDN0 for sim
            if not self.rd4sim and i!=0: 
                continue

            # avoid overwriting
            Qlist = []
            for q in qlist:
                if misctools.check_path(qout.f[q].rdn0[i],overwrite=self.overwrite,verbose=self.verbose):  
                    Qlist.append(q)
            if Qlist != []: 
                continue

            # power spectrum
            cl = { q: np.zeros((2,Lmax+1)) for q in qlist }

            # load alm
            almr = { m: self.Fl[m][:,None]*pickle.load(open(falm[m][i],"rb"))[:self.rlmax+1,:self.rlmax+1] for m in self.mtype }

            # loop for I
            for I in tqdm.tqdm(range(self.rdmin,self.rdmax+1),ncols=100,desc='inside loop:',leave=False):

                gmv, cmv = 0., 0.

                # load alm
                alms = { m: self.Fl[m][:,None]*pickle.load(open(falms[m][I],"rb"))[:self.rlmax+1,:self.rlmax+1] for m in self.mtype }

                for q in qlist:

                    X, Y = q[0], q[1]

                    if I==i: continue

                    if q=='MV':
                        glm, clm = gmv.copy(), cmv.copy()
                    else:
                        glm, clm = self.qXY(q,Lmax,almr[X],alms[X],almr[Y],alms[Y])

                    if not self.bhe_do:
                        glm *= Ag[q][:,None]
                    clm *= Ac[q][:,None]

                    cl[q][0,:] += curvedsky.utils.alm2cl(Lmax,glm)
                    cl[q][1,:] += curvedsky.utils.alm2cl(Lmax,clm)

                    # MV
                    if q in self.qMV and 'MV' in qlist:
                        gmv += Wg[q][:,None] * glm
                        cmv += Wc[q][:,None] * clm

            if self.rdsim>0:
                
                sn = self.rdsim
                if self.rdmin<=i and i<=self.rdmax:  sn = self.rdsim-1
                
                for q in qlist:
                    cl[q] = cl[q]/(self.wn[4]*sn) - N0[q]
                    oL = np.linspace(0,Lmax,Lmax+1)
                    np.savetxt(qout.f[q].rdn0[i],np.concatenate((oL[None,:],cl[q])).T)


    
    def qXY(self,q,Lmax,Xlm1,Xlm2,Ylm1,Ylm2,gtype='k'):# for N0 and RDN0 estimates
    
        rlmin = self.rlmin
        rlmax = self.rlmax
        nside = self.nside
        lcl   = self.lcl

        glm1, glm2, tlm1, tlm2, slm1, slm2 = 0., 0., 0., 0., 0., 0.
        if self.qtype=='lens' or 'lens' in self.bhe_list:
            if q=='TT':
                glm1, clm1 = curvedsky.rec_lens.qtt(Lmax,rlmin,rlmax,lcl[0,:],Xlm1,Ylm2,gtype=gtype,nside_t=nside)
                glm2, clm2 = curvedsky.rec_lens.qtt(Lmax,rlmin,rlmax,lcl[0,:],Xlm2,Ylm1,gtype=gtype,nside_t=nside)
            if q=='TE':
                glm1, clm1 = curvedsky.rec_lens.qte(Lmax,rlmin,rlmax,lcl[3,:],Xlm1,Ylm2,gtype=gtype,nside_t=nside)
                glm2, clm2 = curvedsky.rec_lens.qte(Lmax,rlmin,rlmax,lcl[3,:],Xlm2,Ylm1,gtype=gtype,nside_t=nside)
            if q=='TB':
                glm1, clm1 = curvedsky.rec_lens.qtb(Lmax,rlmin,rlmax,lcl[3,:],Xlm1,Ylm2,gtype=gtype,nside_t=nside)
                glm2, clm2 = curvedsky.rec_lens.qtb(Lmax,rlmin,rlmax,lcl[3,:],Xlm2,Ylm1,gtype=gtype,nside_t=nside)
            if q=='EE':
                glm1, clm1 = curvedsky.rec_lens.qee(Lmax,rlmin,rlmax,lcl[1,:],Xlm1,Ylm2,gtype=gtype,nside_t=nside)
                glm2, clm2 = curvedsky.rec_lens.qee(Lmax,rlmin,rlmax,lcl[1,:],Xlm2,Ylm1,gtype=gtype,nside_t=nside)
            if q=='EB':
                glm1, clm1 = curvedsky.rec_lens.qeb(Lmax,rlmin,rlmax,lcl[1,:],Xlm1,Ylm2,gtype=gtype,nside_t=nside)
                glm2, clm2 = curvedsky.rec_lens.qeb(Lmax,rlmin,rlmax,lcl[1,:],Xlm2,Ylm1,gtype=gtype,nside_t=nside)

            if not self.bhe_do:
                return glm1+glm2, clm1+clm2

        if self.qtype=='rot':
            if q=='TB':
                rlm1 = curvedsky.rec_rot.qtb(Lmax,rlmin,rlmax,lcl[3,:],Xlm1,Ylm2,nside_t=nside)
                rlm2 = curvedsky.rec_rot.qtb(Lmax,rlmin,rlmax,lcl[3,:],Xlm2,Ylm1,nside_t=nside)
            if q=='EB':
                rlm1 = curvedsky.rec_rot.qeb(Lmax,rlmin,rlmax,lcl[1,:],Xlm1,Ylm2,nside_t=nside)
                rlm2 = curvedsky.rec_rot.qeb(Lmax,rlmin,rlmax,lcl[1,:],Xlm2,Ylm1,nside_t=nside)

            return rlm1+rlm2, (rlm1+rlm2)*0.

        if self.qtype=='tau' or 'tau' in self.bhe_list:
            if q=='TT':
                tlm1 = curvedsky.rec_tau.qtt(Lmax,rlmin,rlmax,lcl[0,:],Xlm1,Ylm2,nside_t=nside)
                tlm2 = curvedsky.rec_tau.qtt(Lmax,rlmin,rlmax,lcl[0,:],Xlm2,Ylm1,nside_t=nside)
            if q=='EB':
                tlm1 = curvedsky.rec_tau.qeb(Lmax,rlmin,rlmax,lcl[1,:],Xlm1,Ylm2,nside_t=nside)
                tlm2 = curvedsky.rec_tau.qeb(Lmax,rlmin,rlmax,lcl[1,:],Xlm2,Ylm1,nside_t=nside)

            if not self.bhe_do:
                return tlm1+tlm2, (tlm1+tlm2)*0.

        if self.qtype=='src' or 'src' in self.bhe_list:
            if q=='TT':
                slm1 = curvedsky.rec_src.qtt(Lmax,rlmin,rlmax,Xlm1,Ylm2,nside_t=nside)
                slm2 = curvedsky.rec_src.qtt(Lmax,rlmin,rlmax,Xlm2,Ylm1,nside_t=nside)

            if not self.bhe_do:
                return slm1+slm2, (slm1+slm2)*0.

        # Bias hardened estimator (This alm is already normalized)
        if self.bhe_do:
            alm1 = self.bhe_c[q]['tau'][:,None]*tlm1 + self.bhe_c[q]['lens'][:,None]*glm1 + self.bhe_c[q]['src'][:,None]*slm1
            alm2 = self.bhe_c[q]['tau'][:,None]*tlm2 + self.bhe_c[q]['lens'][:,None]*glm2 + self.bhe_c[q]['src'][:,None]*slm2
            return alm1+alm2, (alm1+alm2)*0.


    def mean(self):

        Lmax = self.olmax
        oL   = np.linspace(0,Lmax,Lmax+1)
        rlz  = np.linspace(self.mfmin,self.mfmax,self.mfmax-self.mfmin+1,dtype=np.int)

        for q in self.qlist:

            if misctools.check_path(self.f[q].mf,overwrite=self.overwrite,verbose=self.verbose): continue

            mfg, mfc = 0., 0.
            for I in tqdm.tqdm(rlz,ncols=100,desc='mean-field (all sim average): ('+q+')'):
                mfgi, mfci = pickle.load(open(self.f[q].alm[I],"rb"))
                mfg += mfgi/self.mfsim
                mfc += mfci/self.mfsim

            pickle.dump((mfg,mfc),open(self.f[q].mf,"wb"),protocol=pickle.HIGHEST_PROTOCOL)

            # compute mf cls
            if verbose:  print('cl for mean field bias')
            cl = np.zeros((2,Lmax+1))
            cl[0,:] = curvedsky.utils.alm2cl(Lmax,mfg)/self.wn[4]
            cl[1,:] = curvedsky.utils.alm2cl(Lmax,mfc)/self.wn[4]
            np.savetxt(self.f[q].mfcl,np.concatenate((oL[None,:],cl)).T)


    def mean_rlz(self):

        Lmax = self.olmax
        oL   = np.linspace(0,Lmax,Lmax+1)

        for q in self.qlist:

            # counting missing files
            filen = 0
            for i in self.rlz:
                if misctools.check_path(self.f[q].mfb[i],overwrite=self.overwrite,verbose=self.verbose): continue
                filen += 1
            if filen == 0: 
                continue  # do nothing below

            mglm = np.zeros((Lmax+1,Lmax+1),dtype=np.complex)
            mclm = np.zeros((Lmax+1,Lmax+1),dtype=np.complex)

            for I in tqdm.tqdm(self.mfrlz,ncols=100,desc='mean-field: load reconstructed alms ('+q+')'):
                glm, clm = pickle.load(open(self.f[q].alm[I],"rb"))
                mglm += glm/self.mfsim
                mclm += clm/self.mfsim

            for i in tqdm.tqdm(self.rlz,ncols=100,desc='mean-field: alm for each rlz ('+q+')'):

                if misctools.check_path(self.f[q].mfb[i],overwrite=self.overwrite,verbose=self.verbose): continue
        
                if i>=self.mfmin and i<=self.mfmax: 
                    glm, clm = pickle.load(open(self.f[q].alm[i],"rb"))
                    mfg = mglm - glm/self.mfsim
                    mfc = mclm - clm/self.mfsim
                    mfg *= self.mfsim/(self.mfsim-1.)
                    mfc *= self.mfsim/(self.mfsim-1.)
                else:
                    mfg = 1.*mglm
                    mfc = 1.*mclm

                pickle.dump((mfg,mfc),open(self.f[q].mfb[i],"wb"),protocol=pickle.HIGHEST_PROTOCOL)

            # compute mf cls
            for i in tqdm.tqdm(self.rlz,ncols=100,desc='mean-field: aps for each rlz ('+q+')'):

                if misctools.check_path(self.f[q].ml[i],overwrite=self.overwrite,verbose=self.verbose): continue

                mfg, mfc = pickle.load(open(self.f[q].mfb[i],"rb"))

                cl = np.zeros((2,Lmax+1))
                cl[0,:] = curvedsky.utils.alm2cl(Lmax,mfg) / self.wn[4]
                cl[1,:] = curvedsky.utils.alm2cl(Lmax,mfc) / self.wn[4]
                np.savetxt(self.f[q].ml[i],np.concatenate((oL[None,:],cl)).T)



    def qrec_flow(self,run=[]):

        # set filtering
        if run:
            self.cinvfilter()

        # normalization
        if 'norm' in run:
            self.al()

        # quadratic estimators
        if 'qrec' in run:
            self.qrec()

        # Realization-independent part of RDN0
        if 'n0' in run:
            self.n0()

        # Realization-dependent part of RDN0
        if 'rdn0' in run:
            self.rdn0()

        # mean-field bias
        if 'mean' in run:
            self.mean_rlz()



class quad_cross(quad): # for cross between two different maps

    def __init__(self,qobj0,qobj1,**kwargs):

        super().__init__(**kwargs)
        
        self.qobj0 = qobj0
        self.qobj1 = qobj1
        
                
    def n0x(self):
        '''
        Cross qobj0 x qobj1 
        N0 for X^{A,1}Y^{A,2} Z^{B,1}W^{B,2} + X^{A,1}Y^{A,2} Z^{B,2}W^{B,1} 
        '''

        # load normalization and weights
        Ag0, Ac0, Wg0, Wc0 = quad.loadnorm(self.qobj0)
        Ag1, Ac1, Wg1, Wc1 = quad.loadnorm(self.qobj1)

        # power spectrum
        cl = {q: np.zeros((2,self.olmax+1)) for q in self.qlist}

        # loop for realizations
        for i in tqdm.tqdm(self.n0rlz,ncols=100,desc='N0 bias (cross):'):

            id0, id1 = 2*i-1, 2*i
            gmv, cmv = 0., 0.

            alm0 = { m: self.qobj0.Fl[m][:,None] * pickle.load(open(self.qobj0.falm[m][id0],"rb"))[:self.rlmax+1,:self.rlmax+1] for m in self.mtype }
            alm1 = { m: self.qobj0.Fl[m][:,None] * pickle.load(open(self.qobj0.falm[m][id1],"rb"))[:self.rlmax+1,:self.rlmax+1] for m in self.mtype }
            blm0 = { m: self.qobj1.Fl[m][:,None] * pickle.load(open(self.qobj1.falm[m][id0],"rb"))[:self.rlmax+1,:self.rlmax+1] for m in self.mtype }
            blm1 = { m: self.qobj1.Fl[m][:,None] * pickle.load(open(self.qobj1.falm[m][id1],"rb"))[:self.rlmax+1,:self.rlmax+1] for m in self.mtype }

            for q in tqdm.tqdm(self.qlist,ncols=100,desc='each quad-comb:',leave=False):

                if q == 'MV':
                    glm, clm = gmv.copy(), cmv.copy()
                else:
                    q1, q2 = q[0], q[1]
                    glm, clm = self.qXYx(q,self.olmax,alm0,alm1,blm0,blm1)

                cl[q][0,:] += Ag0[q]*Ag1[q]*curvedsky.utils.alm2cl(self.olmax,glm)/(2*self.wn[4]*self.n0sim)
                cl[q][1,:] += Ac0[q]*Ac1[q]*curvedsky.utils.alm2cl(self.olmax,clm)/(2*self.wn[4]*self.n0sim)

                # T+P
                if q in self.qMV and 'MV' in self.qlist:
                    gmv += Wg[q][:,None]*glm
                    cmv += Wc[q][:,None]*clm

        for q in self.qlist:
            print ('save N0 data')
            oL = np.linspace(0,self.olmax,self.olmax+1)
            np.savetxt(self.f[q].n0bl,np.concatenate((oL[None,:],cl[q])).T)



    def rdn0x(self,rlz):
        '''
        The sim-data-mixed term of the RDN0 bias calculation
        '''

        Ag0, Ac0, Wg0, Wc0 = quad.loadnorm(self.qobj0)
        Ag1, Ac1, Wg1, Wc1 = quad.loadnorm(self.qobj1)

        # maximum multipole of output
        Lmax  = self.olmax
        qlist = self.qlist
        oL = np.linspace(0,Lmax,Lmax+1)

        # load N0
        N0 = {q: np.loadtxt(self.f[q].n0bl,unpack=True,usecols=(1,2)) for q in qlist}

        # compute RDN0
        for i in tqdm.tqdm(rlz,ncols=100,desc='RDN0:'):
            print(i)

            # power spectrum
            cl = {q: np.zeros((2,Lmax+1)) for q in qlist}

            # load alm
            almr = { m: self.qobj0.Fl[m][:,None]*pickle.load(open(self.qobj0.falm[m][i],"rb"))[:self.rlmax+1,:self.rlmax+1] for m in self.mtype}
            blmr = { m: self.qobj1.Fl[m][:,None]*pickle.load(open(self.qobj1.falm[m][i],"rb"))[:self.rlmax+1,:self.rlmax+1] for m in self.mtype}

            # loop for sim
            for I in tqdm.tqdm(range(self.rdmin,self.rdmax+1),ncols=100,desc='inside loop:',leave=False):

                gmv0, gmv1, cmv0, cmv1 = 0., 0., 0., 0.

                # load alm
                alms = { m: self.qobj0.Fl[m][:,None]*pickle.load(open(self.qobj0.falm[m][I],"rb"))[:self.rlmax+1,:self.rlmax+1] for m in self.mtype }
                blms = { m: self.qobj1.Fl[m][:,None]*pickle.load(open(self.qobj1.falm[m][I],"rb"))[:self.rlmax+1,:self.rlmax+1] for m in self.mtype }

                for q in qlist:

                    q1, q2 = q[0], q[1]

                    if I==i: continue
                    print(I)

                    if q=='MV':
                        glm0, glm1, clm0, clm1 = gmv0.copy(), gmv1.copy(), cmv0.copy(), cmv1.copy()
                    else:
                        glm0, glm1, clm0, clm1 = self.qXYx(q,Lmax,almr,alms,blmr,blms)

                    cl[q][0,:] += Ag0[q]*Ag1[q]*curvedsky.utils.alm2cl(Lmax,glm0,glm1)
                    cl[q][1,:] += Ac0[q]*Ac1[q]*curvedsky.utils.alm2cl(Lmax,clm0,clm1)

                    # T+P
                    if q in self.qMV and 'MV' in qlist:
                        gmv0 += Wg0[q][:,None] * glm0
                        gmv1 += Wg1[q][:,None] * glm1
                        cmv0 += Wc0[q][:,None] * clm0
                        cmv1 += Wc1[q][:,None] * clm1

            if self.rdsim>0:
                
                sn = self.rdsim
                if self.rdmin<=i and i<=self.rdmax:  sn = self.rdsim-1

                for q in qlist:
                    cl[q] = cl[q]/(self.wn[4]*sn) - N0[q]
                    np.savetxt(self.f[q].rdn0[i],np.concatenate((oL[None,:],cl[q])).T)


    def qXYx(self,q,Lmax,almr,alms,blmr,blms):

        rlmin = self.rlmin
        rlmax = self.rlmax
        nside = self.nside
        lcl   = self.lcl
        q1, q2 = q[0], q[1]

        if self.qtype=='rot':
            if q=='EB':
                a01 = curvedsky.rec_rot.qeb(Lmax,rlmin,rlmax,lcl[1,:],almr[q1],alms[q2],nside_t=nside)
                a10 = curvedsky.rec_rot.qeb(Lmax,rlmin,rlmax,lcl[1,:],alms[q1],almr[q2],nside_t=nside)
                b01 = curvedsky.rec_rot.qeb(Lmax,rlmin,rlmax,lcl[1,:],blmr[q1],blms[q2],nside_t=nside)
                b10 = curvedsky.rec_rot.qeb(Lmax,rlmin,rlmax,lcl[1,:],blms[q1],blmr[q2],nside_t=nside)

            return a01+a10, b01+b10, (a01+a10)*0., (b01+b10)*0.



# ////////////////////// #
# Some useful functions  #
# ////////////////////// #

def reconstruction(droot,ids,rlz=[],stag='',getobj=True,run=[],**kwargs):

    """
    Reconstructing CMB lensing potential and its curl mode

    Args:
        :droot (*str*): Root directory of files to be saved
        :ids[] (*str*): 1D array of strings identifying rlz, e.g. 0001, 0002, ...

    Args(optional):
        :rlz[] (*int*): 1D array of integers identifying rlz to be computed
        :stag (*str*): An optional string in order to specify which type of input CMB is used
        :getobj (*bool*): Retrun objects of reconstruction class, containing parameters, filenames
        :run (*str*): Running reconstruction codes
        :**kwargs : Other optional parameters for quad object
    """

    # read parameters
    qobj = quad(rlz=rlz,**kwargs)

    # define filenames from qobj
    qobj.fname(droot,ids,stag)

    # Main calculation
    qobj.qrec_flow(run=run)

    # Return parameters, filenames
    if getobj:
        return qobj

