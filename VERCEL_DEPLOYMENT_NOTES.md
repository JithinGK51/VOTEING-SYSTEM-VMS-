# Vercel Deployment Notes

## ⚠️ Important Limitations

### 1. CSV File Storage
- **Issue:** Vercel's filesystem is read-only. CSV file writes will NOT persist.
- **Impact:** Voter registration, vote casting, and data management features will not work.
- **Solution Required:** Migrate to a database (PostgreSQL, MongoDB) or external storage (S3, Supabase).

### 2. SecuGen Hardware Integration
- **Issue:** SecuGen fingerprint scanner requires USB/localhost access.
- **Impact:** Biometric features will NOT work on Vercel.
- **Current Setup:** App connects to `https://localhost:8443` which is not accessible on Vercel.
- **Solution Required:** 
  - Keep hardware-dependent features for local deployment only
  - Or create a separate backend service for hardware access
  - Or use alternative authentication for web version

### 3. Session Management
- **Note:** Flask sessions may have limitations in serverless environment.
- **Recommendation:** Use serverless-compatible session storage if needed.

## ✅ What Was Modified

1. **Created `vercel.json`** - Vercel configuration file
2. **Updated `requirements.txt`** - Removed `wfastcgi` (only needed for IIS)

## 📋 Deployment Steps

1. **Set Environment Variables in Vercel Dashboard:**
   - `SECRET_KEY` - Generate a secure random string for Flask sessions
   - Any other configuration values needed

2. **Deploy Settings:**
   - Framework Preset: Flask
   - Root Directory: `./`
   - Build Command: (leave empty or `pip install -r requirements.txt`)
   - Output Directory: `N/A`
   - Install Command: `pip install -r requirements.txt`

3. **After Deployment:**
   - Test basic routes (home page should work)
   - CSV-dependent features will fail (expected)
   - Hardware-dependent features will fail (expected)

## 🔧 Recommended Next Steps

### For Full Functionality:
1. **Database Migration:**
   - Set up Vercel Postgres or MongoDB Atlas
   - Replace CSV operations with database queries
   - Update `app.py` to use database instead of CSV

2. **Hardware Access:**
   - Deploy hardware-dependent features separately
   - Use a local server or dedicated backend for SecuGen integration
   - Or implement alternative authentication for web version

3. **Environment Variables:**
   - Move all secrets to Vercel environment variables
   - Update `app.py` to use `os.environ.get()`

## 📝 Current Status

- ✅ Vercel configuration files created
- ⚠️ CSV storage will not work (read-only filesystem)
- ⚠️ SecuGen hardware will not work (no localhost access)
- ✅ Basic Flask app structure is compatible
- ✅ Static templates will work
- ✅ Routes are configured correctly

## 🚀 Deployment Command

After pushing changes to GitHub:
```bash
vercel --prod
```

Or use Vercel dashboard to import from GitHub.

---

**Note:** This deployment is suitable for:
- Testing the web interface
- Demonstrating the UI/UX
- Development and staging environments

**Not suitable for:**
- Production voting system (due to CSV and hardware limitations)
- Full functionality without database migration

