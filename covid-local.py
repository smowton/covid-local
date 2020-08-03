#!/usr/bin/python

import subprocess
import csv
import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.dates
import matplotlib.pyplot as plt
import os.path

data_path = "/home/chris/covid-local.csv"
outdir = "/home/chris/covid-local-site"

with open(data_path, "wb") as f:
  subprocess.check_call(["curl", "-L", "https://coronavirus.data.gov.uk/downloads/csv/coronavirus-cases_latest.csv"], stdout=f)

regions = {}

with open(data_path, "r") as f:
  reader = csv.DictReader(f)
  for rec in reader:
    if len(rec) == 0:
      continue
    region_name, region_type, date_str, cases = rec["Area name"], rec["Area type"], rec["Specimen date"], rec["Daily lab-confirmed cases"]
    date = datetime.datetime.strptime(date_str, '%Y-%m-%d')
    cases = int(cases)
    key = (region_name, region_type)
    if key not in regions:
      regions[key] = []
    regions[key].append((date_str, date, cases))

def last_7_day_avg(end, recs):
  start = end - datetime.timedelta(6)
  return sum(rec[2] for rec in recs if rec[1] <= end and rec[1] >= start) / 7.0

def escape(fname):
  return "".join(c if c.isalpha() else "_" for c in fname)

def pad_series(recs):
  out = []
  day = datetime.timedelta(1)
  for rec in recs:
    if len(out) != 0:
      day_before = rec[1] - day
      while out[-1][1] != day_before:
        next_day = out[-1][1] + day
        out.append((datetime.datetime.strftime(next_day, "%Y-%m-%d"), next_day, 0))
    out.append(rec)
  return out

def write_graph(region_name, region_type, records):
  records = sorted(records, key = lambda rec: rec[1])
  records = pad_series(records)
  records = [(date_str, date, cases, last_7_day_avg(date, records)) for (date_str, date, cases) in records]
  first_date = min(rec[1] for rec in records)
  fname = os.path.join(outdir, escape(region_name + " " + region_type))
  fig, ax = plt.subplots(figsize=(12, 8), dpi=100)
  xvals = [matplotlib.dates.date2num(rec[1]) for rec in records]
  avgvals = [rec[3] for rec in records]
  dayvals = [rec[2] for rec in records]
  ax.plot_date(xvals, avgvals, "b-")
  ax.bar(xvals, dayvals, color = (0.8, 0.8, 0.8, 1.0))
  ax.set(xlabel = "Date", ylabel = "Cases per day", title = region_name)
  fig.savefig(fname)
  plt.close()

def write_index(regions):
  regions_by_type = dict()
  for (region_name, region_type) in regions.iterkeys():
    if region_type not in regions_by_type:
      regions_by_type[region_type] = []
    regions_by_type[region_type].append(region_name)

  with open(os.path.join(outdir, "index.html"), "w") as f:
    f.write("<html><body><h1>Covid cases in England by region</h1>\n")
    for (type, regions) in sorted(regions_by_type.iteritems(), key = lambda kv: len(kv[1])):
      f.write("<h2>Region type: %s</h2>\n<ul>\n" % type)
      for region in sorted(regions):
        f.write('<li><a href="%s">%s</a></li>\n' % (escape(region + " " + type) + ".png", region))
      f.write("</ul>\n<hr/>\n")
    f.write("</body></html>")

for (region_name, region_type), records in regions.iteritems():
  write_graph(region_name, region_type, records)

write_index(regions)
