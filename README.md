# QSR Corporate Jobs

A job board that collects **corporate and support-center jobs** from the big quick-service restaurant brands (McDonald's, Chick-fil-A, Wendy's, Starbucks, Yum!, RBI, Inspire, Chipotle, Domino's and more) into one searchable site.

* **Free to run.** GitHub hosts the site and runs the daily update. You don't need a server or a database.
* **Updates every morning.** Each brand's careers site is checked, restaurant crew jobs are filtered out, and the site is republished.
* **Visitors apply on the brand's own site.** Your board links straight to the official posting.

---

## Set it up (about 15 minutes, no coding)

You need a free GitHub account: https://github.com/signup

### 1. Create the repository
1. On GitHub, click **+** (top right) → **New repository**.
2. Name it something like `qsr-jobs`. Choose **Public** (GitHub Pages is free for public repos). Click **Create repository**.
3. On the new repo page, click **uploading an existing file**.
4. Unzip `qsr-jobs.zip` on your computer, open the `qsr-jobs` folder, select **everything inside it** (including the hidden `.github` folder*), and drag it onto the page. Click **Commit changes**.

\* On a Mac, press `Cmd + Shift + .` in Finder to show hidden folders. On Windows, go to **View → Show → Hidden items** in File Explorer. If the upload skips `.github`, create its two files by hand: **Add file → Create new file**, type the name `.github/workflows/update-jobs.yml`, paste in that file's contents, and commit. Do the same for `find-brand.yml`.

### 2. Turn on the website
1. In your repo, go to **Settings → Pages**.
2. Under **Build and deployment → Source**, choose **GitHub Actions**.

### 3. Let the update job save results
1. Go to **Settings → Actions → General**.
2. Under **Workflow permissions**, choose **Read and write permissions**. Click **Save**.

### 4. Run it for the first time
1. Click the **Actions** tab. If GitHub asks, click **I understand my workflows, go ahead and enable them**.
2. Click **Update jobs and publish site** on the left, then **Run workflow → Run workflow**.
3. Wait about 5–15 minutes until you see a green check. The first run is the slowest.
4. Your site is now live at **`https://YOUR-USERNAME.github.io/qsr-jobs/`**. The link is also shown under **Settings → Pages**.

From now on it updates by itself every morning.

---

## Checking that every brand is working
Open your site and scroll to **Sources & last update** at the bottom:

* 🟢 **Green**: the brand is working. You'll see how many corporate jobs it found.
* 🔴 **Red**: that brand's careers site couldn't be read. Yesterday's jobs for that brand stay up, so the site never goes blank.
* ⚪ **Grey**: you've turned the brand off.

Each brand's careers site is different, and companies change systems from time to time. Several brands in `brands.yaml` are marked **best guess**. They were set up from each brand's public careers site but couldn't be test-run before delivery. If one shows red or 0 jobs, use **Fixing or adding a brand** below.

## Fixing or adding a brand
1. Find the brand's careers page, e.g. `https://www.wingstop.com/careers`.
2. Go to **Actions → Find a brand's settings → Run workflow**. Enter the brand name and the careers page URL, then click **Run workflow**.
3. When it finishes, click the run. The summary shows a few lines to copy.
4. Open `brands.yaml` in your repo, click the ✏️ pencil, paste the lines at the bottom (replace the old entry if you're fixing a brand), and click **Commit changes**. The site rebuilds automatically.

To turn a brand off, add `enabled: false` under it in `brands.yaml`.

## Changing what counts as "corporate"
Open `scraper/classify.py`. Near the top there's a plain list of job titles that are treated as restaurant jobs and removed (crew member, cashier, shift supervisor, and so on). Add or remove words and commit. Job functions (Technology, Marketing, Finance…) are defined further down in the same file.

## Using your own domain
In **Settings → Pages → Custom domain**, enter your domain (e.g. `qsrjobs.com`), then follow GitHub's instructions to add a DNS record with your domain registrar.

---

## How it works (for the curious)

```
brands.yaml ──► scraper (runs daily on GitHub) ──► site/data/jobs.json ──► site/index.html (GitHub Pages)
```

| Careers system | Used by (examples) | How it's read |
|---|---|---|
| iCIMS | Wendy's, Chick-fil-A | Public job-search pages |
| SmartRecruiters | Domino's | Public postings API |
| Greenhouse | sweetgreen | Public job-board API |
| Workday | Starbucks and many others | The careers site's own job-search feed |
| Lever | — | Public postings API |
| Branded careers sites | McDonald's, Chipotle, Inspire, Yum!, RBI, Shake Shack | The site map plus the standard job data each posting page publishes for Google Jobs |

The scraper only reads public listings, waits briefly between requests, and keeps track of postings it has already seen so it doesn't download them again. Before adding brands, check each careers site's terms of use. Keep the request rate low, as it is now.

**Run it on your own computer (optional):**
```
pip install -r requirements.txt
python -m scraper.run                  # all brands
python -m scraper.run --only "Wendy's" # one brand
python -m unittest discover tests      # offline tests
cd site && python -m http.server       # then open http://localhost:8000
```
