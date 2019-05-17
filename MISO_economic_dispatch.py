from datetime import datetime
#import matplotlib.pyplot as plt
import numpy as np
import os
import pandas as pd
from pathlib import Path
#import seaborn as sns
import urllib.request
import zipfile

downloads = Path.cwd() / 'downloads'
inputFolder = Path.cwd() / 'inputs'
df_dtypes = {'Region': 'category', 'Owner Code': 'uint32', 'Unit Code': 'uint16', 'Unit Type': 'uint8', 'Date/Time Beginning (EST)': 'category', 'Date/Time End (EST)': 'category', 'Economic Max': 'float32', 'Economic Min': 'float32', 'Emergency Max': 'float32', 'Emergency Min': 'float32', 'Economic Flag': 'uint8', 'Emergency Flag': 'uint8', 'Must Run Flag': 'uint8', 'Unit Available Flag': 'uint8', 'Self Scheduled MW': 'float32', 'Target MW Reduction': 'float32', 'MW': 'float32', 'LMP': 'float32', 'Curtailment Offer Price': 'float32', 'Price1': 'float32', 'MW1': 'float32', 'Price2': 'float32', 'MW2': 'float32', 'Price3': 'float32', 'MW3': 'float32', 'Price4': 'float32', 'MW4': 'float32', 'Price5': 'float32', 'MW5': 'float32', 'Price6': 'float32', 'MW6': 'float32', 'Price7': 'float32', 'MW7': 'float32', 'Price8': 'float32', 'MW8': 'float32', 'Price9': 'float32', 'MW9': 'float32', 'Price10': 'float32', 'MW10': 'float32', 'Slope': 'uint8'} #reduce dataframe size upon import from csv
solar_dtypes = {'Hour': 'str', '01': 'uint16', '02': 'uint16', '03': 'uint16', '04': 'uint16', '05': 'uint16', '06': 'uint16', '07': 'uint16', '08': 'uint16', '09': 'uint16', '10': 'uint16', '11': 'uint16', '12': 'uint16'}

directories = ['downloads','inputs','outputs']
for d in directories: #if the directories don't exist, create them
    directory = Path.cwd() / d
    if not directory.exists():
        os.makedirs(d)
        print('  '+str(d)+' directory created.')

def tmpDelete(f): #delete any temporary files in folder (f)
    dirPath = Path.cwd() / f
    fileList = os.listdir(dirPath)
    if not fileList:
        pass
    else:
        for fileName in fileList:
            os.remove(dirPath / fileName)


print('Select date to analyze (Format: YYYYMMDD)') #request date for analysis
date = input('  >')
month = str(date[4:6])

#setup carbon price input
co2_price = [5,10,25,50]
#co2_price = float(input('Enter carbon price ($/metric ton) or enter "0" to skip carbon price scenario: '))

#setup solar input
#solar_scenario = input('Do you wish to upload a solar scenario (Y/N)? ')

print('Loading solar data...')
solar = pd.read_csv(inputFolder / 'solar_1500MW.csv', dtype=solar_dtypes) #upload solar data
solar = solar[['Hour',month]] #select the hourly data for the current month
solar.rename(index=str, columns={month:'Output'}, inplace=True)


solar15 = pd.read_csv(inputFolder / 'solar_15GW.csv', dtype=solar_dtypes) #upload solar data
solar15 = solar15[['Hour',month]] #select the hourly data for the current month
solar15.rename(index=str, columns={month:'Output'}, inplace=True)

tmpDelete('outputs')
tmpDelete('downloads')

#download day-ahead cleared offer data
urllib.request.urlretrieve('https://docs.misoenergy.org/marketreports/'+date+'_da_co.zip', downloads / 'DACO.zip') 
zipfile.ZipFile(downloads / 'DACO.zip', 'r').extractall(downloads) #extract zip file
os.remove(downloads / 'DACO.zip') #delete zip file
dafile = str(date+'_da_co.csv')

read = pd.read_csv(downloads / dafile, dtype=df_dtypes) #create dataframe from csv

EnergyBids = read[read['Unit Available Flag'] == 1] #drop all bids from generators that are unavailable
EnergyBids = EnergyBids.reset_index()

EnergyBids.rename(index=str, columns={'Date/Time Beginning (EST)':'Hour'}, inplace=True) #rename column to Hour

interval = EnergyBids['Hour'].apply(lambda x: datetime.strptime(x, '%m/%d/%Y %H:%M:%S')) #parse times from each row of data
EnergyBids['Hour'] = interval.apply(lambda x: datetime.strftime(x, '%H')) #set date for each row
EnergyBids['Hour'].astype(str) #convert hour number to string

#Generators can bid above their Pmax, so need to adjust bids so that they cannot be above the economic Pmax
print('Capping all economic bids at generator Pmax...')
for i in range(1,11):
        mask = (EnergyBids['MW'+str(i)] > EnergyBids['Economic Max']).tolist() #create a boolean list if bid > max
        maskList = [i for i, x in enumerate(mask) if x] #create list of indices where condition is true
        for n in maskList:
                EnergyBids.loc[EnergyBids.index[n],'MW'+str(i)] = EnergyBids.loc[EnergyBids.index[n],'Economic Max'] #replace the bid qty with the economic max

#Generators can bid below their Pmin, so need to adjust bids so that none are below their Economic Pmin
print('Raising all economic bids to Pmin...')
for i in range(1,11):
        mask = ((EnergyBids['Economic Flag'] == 1) & (EnergyBids['MW'+str(i)] < EnergyBids['Economic Min'])).tolist() #create a boolean list if the bid is less than economic min for all economic-participating generators
        maskList = [i for i, x in enumerate(mask) if x] #create list of indices where condition is true
        for n in maskList:
                EnergyBids.loc[EnergyBids.index[n],'MW'+str(i)] = EnergyBids.loc[EnergyBids.index[n],'Economic Min'] #replace the bid qty with the economic min
                EnergyBids.loc[EnergyBids.index[n],'Price'+str(i)] = EnergyBids.loc[EnergyBids.index[n],'Price'+str(i+1)] #replace the bid price with the next highest bid price

#If generators are classified as "must run", adjust their bids under their Emergency Min threshold to have a bid price of -$9999 so that they are always dispatched
print('Adjusting all must-run generator bids...')
for i in range(1,11):
        mask = ((EnergyBids['Must Run Flag'] == 1) & (EnergyBids['MW'+str(i)] <= EnergyBids['Emergency Min'])).tolist() #create boolean list if generator is classified as must-run and the bid qty is less than its emergency min
        maskList = [i for i, x in enumerate(mask) if x] #create list of indices where condition is true
        for n in maskList:
                EnergyBids.loc[EnergyBids.index[n],'MW'+str(i)] = EnergyBids.loc[EnergyBids.index[n],'Emergency Min'] #replace the bid qty with the emergency min
                EnergyBids.loc[EnergyBids.index[n],'Price'+str(i)] = -9999 #replace the bid price with -9999

#MISO reports bid increments cumulatively, so I need to subtract each column to get incremental bids
#convert cumulative bid quantity into marginal bid quantity
print('Correcting marginal bids...')
segment = [10,9,8,7,6,5,4,3,2,1]
for s in segment:
        if s>1:
                EnergyBids['MW'+str(s)] = abs(EnergyBids['MW'+str(s)]) - abs(EnergyBids['MW'+str(segment[segment.index(s-1)])]) #subtract bid N-1 qty from bid N qty. Use of absolute values corrects for negative DR bids
                EnergyBids.loc[EnergyBids['MW'+str(s)] < 0, 'MW'+str(s)] = 0 #replace any negative quantities with 0 bids
        elif s==1:
                EnergyBids['MW'+str(s)] = abs(EnergyBids['MW'+str(s)])
        else:        
                break

#Change all negative dispatch to positive
EnergyBids['MW'] = abs(EnergyBids['MW'])

#add emissions rate
print('Adding emissions data...')
UnitTypes = pd.read_csv(inputFolder / 'units.csv') #create dataframe from csv
EnergyBids = EnergyBids.merge(UnitTypes,on='Unit Type') #merge unit emissions data with bid data

#create emmissions outputs
EnergyBids['E1'] = EnergyBids['Emissions Rate']*EnergyBids['MW1']
EnergyBids['E2'] = EnergyBids['Emissions Rate']*EnergyBids['MW2']
EnergyBids['E3'] = EnergyBids['Emissions Rate']*EnergyBids['MW3']
EnergyBids['E4'] = EnergyBids['Emissions Rate']*EnergyBids['MW4']
EnergyBids['E5'] = EnergyBids['Emissions Rate']*EnergyBids['MW5']
EnergyBids['E6'] = EnergyBids['Emissions Rate']*EnergyBids['MW6']
EnergyBids['E7'] = EnergyBids['Emissions Rate']*EnergyBids['MW7']
EnergyBids['E8'] = EnergyBids['Emissions Rate']*EnergyBids['MW8']
EnergyBids['E9'] = EnergyBids['Emissions Rate']*EnergyBids['MW9']
EnergyBids['E10'] = EnergyBids['Emissions Rate']*EnergyBids['MW10']

#add unit type data to each bid
EnergyBids['U1'] = EnergyBids['Unit Type'] * ((EnergyBids['MW1'] * 0) +1) #only add unit data if there is a corresponding bid (otherwise messes up stacking)
EnergyBids['U2'] = EnergyBids['Unit Type'] * ((EnergyBids['MW2'] * 0) +1)
EnergyBids['U3'] = EnergyBids['Unit Type'] * ((EnergyBids['MW3'] * 0) +1)
EnergyBids['U4'] = EnergyBids['Unit Type'] * ((EnergyBids['MW4'] * 0) +1)
EnergyBids['U5'] = EnergyBids['Unit Type'] * ((EnergyBids['MW5'] * 0) +1)
EnergyBids['U6'] = EnergyBids['Unit Type'] * ((EnergyBids['MW6'] * 0) +1)
EnergyBids['U7'] = EnergyBids['Unit Type'] * ((EnergyBids['MW7'] * 0) +1)
EnergyBids['U8'] = EnergyBids['Unit Type'] * ((EnergyBids['MW8'] * 0) +1)
EnergyBids['U9'] = EnergyBids['Unit Type'] * ((EnergyBids['MW9'] * 0) +1)
EnergyBids['U10'] = EnergyBids['Unit Type'] * ((EnergyBids['MW10'] * 0) +1)

#add some calculations related to the actual historical dispatch
EnergyBids['E_act'] = EnergyBids['Emissions Rate']*EnergyBids['MW']
EnergyBids['Cost'] = EnergyBids['LMP'] * EnergyBids['MW']

def market_clearing(): #Calculate what percent of demand cleared in the day-ahead market compared to RTM
        print('Calculating percent of demand cleared in the day-ahead market...')
        urllib.request.urlretrieve('https://docs.misoenergy.org/marketreports/'+date+'_rt_co.zip', downloads / 'RTCO.zip') #download realtime data
        zipfile.ZipFile(downloads / 'RTCO.zip', 'r').extractall(downloads) #extract zip file
        os.remove(downloads / 'RTCO.zip') #delete zip file
        rtfile = str(date+'_rt_co.csv')

        rtco = pd.read_csv(downloads / rtfile) #create dataframe from csv

        rtco.rename(index=str, columns={'Mkthour Begin (EST)':'Hour'}, inplace=True) #rename column to Hour
        interval = rtco['Hour'].apply(lambda x: datetime.strptime(x, '%m/%d/%Y %H:%M:%S')) #parse times from each row of data
        rtco['Hour'] = interval.apply(lambda x: datetime.strftime(x, '%H')) #set date for each row
        rtco['Hour'].astype(str) #convert hour number to string

        hours = ['00','01','02','03','04','05','06','07','08','09','10','11','12','13','14','15','16','17','18','19','20','21','22','23']
        dataframe = pd.DataFrame(index=hours,columns=['MW_sum']) #create empty dataframe
        for hh in hours:
                rtco_hour = rtco.loc[rtco.loc[:,'Hour'] == hh] #retrieve the RTM data for the given hour
                daco_hour = EnergyBids.loc[EnergyBids.loc[:,'Hour'] == hh] #retrieve the DAM data for the given hour
                daco_hour = daco_hour[['Unit Code','MW']] #drop all DAM data except the unit code and cleared MW
                merged = rtco_hour.merge(daco_hour, left_on='Unit Code', right_on='Unit Code', how='left') #add DA cleared MW to RTM data, matched by unit code
                merged['MW'].fillna(0) #if unit did not bid in DAM, then replace NA with 0
                for i in range(1,13): #for each five minute interval
                        merged['Cleared MW'+str(i)] = abs(merged['Cleared MW'+str(i)] - merged['MW']) #find the magnitude of difference between the MW cleared in RTM and DAM
                merged['MW_sum'] = merged.loc[:,'Cleared MW1':'Cleared MW12':2].sum(axis=1) / 12 #sum all 12 5-min intervals and divide by 12 to get MWh
                hourly_sum = merged.loc[:,'MW_sum'].sum() #find the sum of RTM cleared MW for the given hour
                dataframe.loc[hh,'MW_sum'] = hourly_sum #add the sum to the main dataframe
        rt_sum = dataframe.loc[:,'MW_sum'].sum() #find the sum of RTM cleared MW for the entire day
        da_sum = EnergyBids.loc[:,'MW'].sum() #fiind the sum of DAM cleared MW for the entire day
        tot_sum = rt_sum + da_sum #find the total MW cleared in both markets
        da_percent = da_sum / tot_sum
        print('Date: {}'.format(date), file=open('outputs/DA_percent.txt','a'))
        #print('Carbon Price: {}'.format(co2_price), file=open('outputs/DA_percent.txt','a'))
        #print('Solar Scenario? {}'.format(solar_scenario), file=open('outputs/DA_percent.txt','a'))
        print('{:01.1%} percent of demand ({:,.0f} of {:,.0f} MW) cleared in day-ahead market'.format(da_percent,da_sum,tot_sum), file=open('outputs/DA_percent.txt','a'))
        print('Only {:,.0f} MW cleared in RTM'.format(rt_sum), file=open('outputs/DA_percent.txt','a'))
                
market_clearing()

def dispatch(fileName, carbonPrice=0, EnergyBids=EnergyBids, solar_sc=False, solarFile=solar):
        print('Calculating '+str(fileName)+' scenario dispatch (this will take several minutes)...')
        hours = ['00','01','02','03','04','05','06','07','08','09','10','11','12','13','14','15','16','17','18','19','20','21','22','23']
        dataframe = pd.DataFrame(index=hours,columns=['Demand','MCE','Total Ems','Avg Ems','Marginal Ems']) #create empty dataframe
        for hh in hours: #for each hour of the day, calculate the dispatch
                #find total demand
                if solar_sc==True: #only adjust the demand shape under the solar scenario
                        demand = EnergyBids.loc[EnergyBids.loc[:,'Hour'] == hh,'MW'].sum() - solarFile.loc[solarFile.loc[:,'Hour'] == hh,'Output']
                        demand = float(demand)
                        SL = int(solarFile.loc[solarFile.loc[:,'Hour'] == hh,'Output'])       
                else:
                        demand = EnergyBids.loc[EnergyBids.loc[:,'Hour'] == hh,'MW'].sum() #sum the total MW that was dispatched according to the historic data
                        SL = 0

                #create a stack of prices
                EnergyBids_prices = EnergyBids.loc[EnergyBids.loc[:,'Hour'] == hh,'Price1':'MW10':2].stack()
                EnergyBids_prices = EnergyBids_prices.reset_index()
                EnergyBids_prices = pd.DataFrame(EnergyBids_prices)

                #create a stack of MW bids
                EnergyBids_qtys = EnergyBids.loc[EnergyBids.loc[:,'Hour'] == hh,'MW1':'MW10':2].stack()
                EnergyBids_qtys = EnergyBids_qtys.reset_index()
                EnergyBids_qtys = pd.DataFrame(EnergyBids_qtys)

                #create a stack of unit emissions
                EnergyBids_Ems = EnergyBids.loc[EnergyBids.loc[:,'Hour'] == hh,'E1':'E10'].stack()
                EnergyBids_Ems = EnergyBids_Ems.reset_index()
                EnergyBids_Ems = pd.DataFrame(EnergyBids_Ems)

                #create a stack of unit types
                EnergyBids_unit = EnergyBids.loc[EnergyBids.loc[:,'Hour'] == hh,'U1':'U10'].stack()
                EnergyBids_unit = EnergyBids_unit.reset_index()
                EnergyBids_unit = pd.DataFrame(EnergyBids_unit)

                #merge stacked data into one dataframe
                EnergyBids_only = pd.DataFrame(EnergyBids_prices.iloc[:,2])
                EnergyBids_only['qty'] = EnergyBids_qtys.iloc[:,2]
                EnergyBids_only['ems'] = EnergyBids_Ems.iloc[:,2]
                EnergyBids_only['unit'] = EnergyBids_unit.iloc[:,2]
                EnergyBids_only.columns = ['price','qty','ems','unit']

                #add carbon price
                EnergyBids_only['price'] = EnergyBids_only['price'] + (EnergyBids_only['ems'] / EnergyBids_only['qty'] * carbonPrice)

                #create new dataframe sorted by price
                df = EnergyBids_only.sort_values(by='price', ascending=True)

                #create a column for cumulative bid
                df['cumulative'] = np.zeros(df.shape[0])
                for i in range(1,df.shape[0]):
                        df.iloc[i,4] = df.iloc[i-1,4] + df.iloc[i,1]

                df = df.reset_index(drop=True) #reset the index

                #find Marginal Cost of Energy
                clear = int(df[df['cumulative']>=demand].index[0]) #find the position of cumulative demand that equals or is just greater than cleared demand
                mce = df.iloc[clear,0] #find the marginal cost of energy

                #find the amount of energy cleared at the marginal unit
                marg_MW = demand - df.iloc[clear-1,4]
                
                #find total emissions
                tot_ems = df.iloc[:clear,2].sum()  + (marg_MW / df.iloc[clear,1]) * df.iloc[clear,2]

                #find average emissions
                avg_ems = tot_ems / demand

                #find marginal unit
                marg_unit = df.iloc[clear,3]

                #find resource mix
                df_RM = df.iloc[:clear]
                ST = df_RM[df_RM['unit'] == 4].sum()['qty'] + (marg_MW if marg_unit == 4 else 0) #Steam Turbine
                CC = (df_RM[df_RM['unit'] == 5].sum()['qty'] + df_RM[df_RM['unit'] == 51].sum()['qty'] + df_RM[df_RM['unit'] == 52].sum()['qty']) + (marg_MW if marg_unit == (5 or 51 or 52) else 0) #Combined Cycle: add CC single shaft, steam part, turbine part
                GT = df_RM[df_RM['unit'] == 27].sum()['qty'] + (marg_MW if marg_unit == 27 else 0) #Gas Turbine
                IC = df_RM[df_RM['unit'] == 31].sum()['qty'] + (marg_MW if marg_unit == 31 else 0) #Internal Combustion
                OF = df_RM[df_RM['unit'] == 71].sum()['qty']  + (marg_MW if marg_unit == 71 else 0) #Other Fossil
                OP = df_RM[df_RM['unit'] == 72].sum()['qty'] + (marg_MW if marg_unit == 72 else 0) #Other Peaker
                HY = (df_RM[df_RM['unit'] == 41].sum()['qty'] + df_RM[df_RM['unit'] == 42].sum()['qty']) + (marg_MW if marg_unit == (41 or 42) else 0) #Hydro: add hydro plus pumped storage
                WD = df_RM[df_RM['unit'] == 61].sum()['qty'] + (marg_MW if marg_unit == 61 else 0) #Wind
                DR = (df_RM[df_RM['unit'] == 87].sum()['qty'] + df_RM[df_RM['unit'] == 88].sum()['qty']) + (marg_MW if marg_unit == (87 or 88) else 0) #DR
                

                #add new row to dataframe
                dataframe.loc[hh,'Demand'] = demand
                dataframe.loc[hh,'MCE'] = mce
                dataframe.loc[hh,'Total Ems'] = tot_ems
                dataframe.loc[hh,'Avg Ems'] = avg_ems
                dataframe.loc[hh,'Marginal Ems'] = marg_unit
                dataframe.loc[hh,'Steam Turbine'] = ST
                dataframe.loc[hh,'Combined Cycle'] = CC
                dataframe.loc[hh,'Gas Turbine'] = GT
                dataframe.loc[hh,'Internal Combustion'] = IC 
                dataframe.loc[hh,'Other Fossil'] = OF
                dataframe.loc[hh,'Other Peaker'] = OP
                dataframe.loc[hh,'Hydro'] = HY
                dataframe.loc[hh,'Wind'] = WD 
                dataframe.loc[hh,'DR'] = DR
                dataframe.loc[hh,'Solar'] = SL

                '''
                df['unit'].astype('category')
                ax = sns.scatterplot(x = "cumulative", y = "price", hue = "unit", markers="+", data = df)
                ax.set_title('supply curve for fleet for hour starting '+str(hh)+':00')
                ax.axvline(demand)
                plt.show()
                '''
        #export dataframe to csv file
        print('Exporting '+str(fileName)+' scenario results...')
        with open(Path.cwd() / ('outputs/' + fileName +'_' + str(carbonPrice) + '_hourly.csv'),'w') as f:    
                dataframe.to_csv(f, header=True, index=True)
        return dataframe

def actual(EnergyBids=EnergyBids):
        hours = ['00','01','02','03','04','05','06','07','08','09','10','11','12','13','14','15','16','17','18','19','20','21','22','23']
        dataframe = pd.DataFrame(index=hours,columns=['Demand','Total Ems','Avg Ems']) #create empty dataframe
        for hh in hours: #for each hour of the day, calculate the dispatch
                #find total demand
                demand = EnergyBids.loc[EnergyBids.loc[:,'Hour'] == hh,'MW'].sum() #sum the total MW that was dispatched according to the historic data

                #find total emissions
                tot_ems = EnergyBids.loc[EnergyBids.loc[:,'Hour'] == hh,'E_act'].sum()

                #find average emissions
                avg_ems = tot_ems / demand

                #find cost of each dispatch
                tot_cost = EnergyBids.loc[EnergyBids.loc[:,'Hour'] == hh,'Cost'].sum()
                avg_cost = tot_cost / demand

                #find resource mix
                df_RM = EnergyBids.loc[EnergyBids.loc[:,'Hour'] == hh] #retrieve a slice of all bids in the specified hour
                ST = df_RM[df_RM['Unit Type'] == 4].sum()['MW'] #Steam Turbine
                CC = (df_RM[df_RM['Unit Type'] == 5].sum()['MW'] + df_RM[df_RM['Unit Type'] == 51].sum()['MW'] + df_RM[df_RM['Unit Type'] == 52].sum()['MW']) #Combined Cycle: add CC single shaft, steam part, turbine part
                GT = df_RM[df_RM['Unit Type'] == 27].sum()['MW'] #Gas Turbine
                IC = df_RM[df_RM['Unit Type'] == 31].sum()['MW'] #Internal Combustion
                OF = df_RM[df_RM['Unit Type'] == 71].sum()['MW'] #Other Fossil
                OP = df_RM[df_RM['Unit Type'] == 72].sum()['MW'] #Other Peaker
                HY = (df_RM[df_RM['Unit Type'] == 41].sum()['MW'] + df_RM[df_RM['Unit Type'] == 42].sum()['MW']) #Hydro: add hydro plus pumped storage
                WD = df_RM[df_RM['Unit Type'] == 61].sum()['MW'] #Wind
                DR = abs((df_RM[df_RM['Unit Type'] == 87].sum()['MW'] + df_RM[df_RM['Unit Type'] == 88].sum()['MW'])) #DR
                SL = 0

                #add new row to dataframe
                dataframe.loc[hh,'Demand'] = demand
                dataframe.loc[hh,'Total Ems'] = tot_ems
                dataframe.loc[hh,'Avg Ems'] = avg_ems
                dataframe.loc[hh,'Total Cost'] = tot_cost
                dataframe.loc[hh,'Avg Cost'] = avg_cost
                dataframe.loc[hh,'Steam Turbine'] = ST
                dataframe.loc[hh,'Combined Cycle'] = CC
                dataframe.loc[hh,'Gas Turbine'] = GT
                dataframe.loc[hh,'Internal Combustion'] = IC 
                dataframe.loc[hh,'Other Fossil'] = OF
                dataframe.loc[hh,'Other Peaker'] = OP
                dataframe.loc[hh,'Hydro'] = HY
                dataframe.loc[hh,'Wind'] = WD 
                dataframe.loc[hh,'DR'] = DR
                dataframe.loc[hh,'Solar'] = SL
        print('Exporting historical results...')
        with open(Path.cwd() / ('outputs/actual_hourly.csv'),'w') as f:    
                dataframe.to_csv(f, header=True, index=True)
        return dataframe

#extract data about actual dispatch
print('Extracting actual dispatch data')
historic = actual()

#create actual summary stats for the day
act_summary = pd.DataFrame(index=['Actual'],columns=['Energy','Cost','Emissions','Avg Ems Rate']) #create new dataframe
act_summary.loc['Actual','Energy'] = historic['Demand'].sum() #find total energy consumption
act_summary.loc['Actual','Cost'] = historic['Total Cost'].sum() #find the total cost of generation
act_summary.loc['Actual','Emissions'] = historic['Total Ems'].sum() #find total emissions
act_summary.loc['Actual','Avg Ems Rate'] = act_summary.loc['Actual','Emissions'] / act_summary.loc['Actual','Energy'] #find average emissions rate
act_summary.loc['Actual','Steam Turbine'] = historic['Steam Turbine'].sum() / act_summary.loc['Actual','Energy'] #find resource mix for steam turbine
act_summary.loc['Actual','Combined Cycle'] = historic['Combined Cycle'].sum() / act_summary.loc['Actual','Energy'] #find resource mix for Combined Cycle
act_summary.loc['Actual','Gas Turbine'] = historic['Gas Turbine'].sum() / act_summary.loc['Actual','Energy'] #find resource mix for Gas Turbine
act_summary.loc['Actual','Internal Combustion'] = historic['Internal Combustion'].sum() / act_summary.loc['Actual','Energy'] #find resource mix for internal combustion
act_summary.loc['Actual','Other Fossil'] = historic['Other Fossil'].sum() / act_summary.loc['Actual','Energy'] #find resource mix for other fossil
act_summary.loc['Actual','Other Peaker'] = historic['Other Peaker'].sum() / act_summary.loc['Actual','Energy'] #find resource mix for other peaker
act_summary.loc['Actual','Hydro'] = historic['Hydro'].sum() / act_summary.loc['Actual','Energy'] #find resource mix for hydro
act_summary.loc['Actual','Wind'] = historic['Wind'].sum() / act_summary.loc['Actual','Energy'] #find resource mix for wind
act_summary.loc['Actual','DR'] = historic['DR'].sum() / act_summary.loc['Actual','Energy'] #find resource mix for DR
act_summary.loc['Actual','Solar'] = historic['Solar'].sum() / act_summary.loc['Actual','Energy'] #find resource mix for DR

#calculate baseline results
base = dispatch('base')

#create summary stats for the day
base_summary = pd.DataFrame(index=['Baseline'],columns=['Energy','Cost','Emissions','Avg Ems Rate']) #create new dataframe
base_summary.loc['Baseline','Energy'] = base['Demand'].sum() #find total energy consumption
cost = base['Demand'] * base['MCE'] #find the cost of generation for each bid
base_summary.loc['Baseline','Cost'] = cost.sum() #find the total cost of generation
base_summary.loc['Baseline','Emissions'] = base['Total Ems'].sum() #find total emissions
base_summary.loc['Baseline','Avg Ems Rate'] = base_summary.loc['Baseline','Emissions'] / base_summary.loc['Baseline','Energy'] #find average emissions rate
base_summary.loc['Baseline','Steam Turbine'] = base['Steam Turbine'].sum() / base_summary.loc['Baseline','Energy'] #find resource mix for steam turbine
base_summary.loc['Baseline','Combined Cycle'] = base['Combined Cycle'].sum() / base_summary.loc['Baseline','Energy'] #find resource mix for Combined Cycle
base_summary.loc['Baseline','Gas Turbine'] = base['Gas Turbine'].sum() / base_summary.loc['Baseline','Energy'] #find resource mix for Gas Turbine
base_summary.loc['Baseline','Internal Combustion'] = base['Internal Combustion'].sum() / base_summary.loc['Baseline','Energy'] #find resource mix for internal combustion
base_summary.loc['Baseline','Other Fossil'] = base['Other Fossil'].sum() / base_summary.loc['Baseline','Energy'] #find resource mix for other fossil
base_summary.loc['Baseline','Other Peaker'] = base['Other Peaker'].sum() / base_summary.loc['Baseline','Energy'] #find resource mix for other peaker
base_summary.loc['Baseline','Hydro'] = base['Hydro'].sum() / base_summary.loc['Baseline','Energy'] #find resource mix for hydro
base_summary.loc['Baseline','Wind'] = base['Wind'].sum() / base_summary.loc['Baseline','Energy'] #find resource mix for wind
base_summary.loc['Baseline','DR'] = base['DR'].sum() / base_summary.loc['Baseline','Energy'] #find resource mix for DR
base_summary.loc['Baseline','Solar'] = base['Solar'].sum() / base_summary.loc['Baseline','Energy'] #find resource mix for DR

Delta = act_summary.append(base_summary) #add baseline summary as row to actual data

#calculate solar scenario results
ss = dispatch('solar', solar_sc=True, solarFile=solar) #run dispatch function with solar data

solar_summary = pd.DataFrame(index=['Solar'],columns=['Energy','Cost','Emissions','Avg Ems Rate']) #create new dataframe
solar_summary.loc['Solar','Energy'] = ss['Demand'].sum() + ss['Solar'].sum() #find total energy consumption
cost = ss['Demand'] * ss['MCE'] #find the cost of generation for each bid
solar_summary.loc['Solar','Cost'] = cost.sum() #find the total cost of generation
solar_summary.loc['Solar','Emissions'] = ss['Total Ems'].sum() #find total emissions
solar_summary.loc['Solar','Avg Ems Rate'] = solar_summary.loc['Solar','Emissions'] / solar_summary.loc['Solar','Energy'] #find average emissions rate
solar_summary.loc['Solar','Steam Turbine'] = ss['Steam Turbine'].sum() / solar_summary.loc['Solar','Energy'] #find resource mix for steam turbine
solar_summary.loc['Solar','Combined Cycle'] = ss['Combined Cycle'].sum() / solar_summary.loc['Solar','Energy'] #find resource mix for Combined Cycle
solar_summary.loc['Solar','Gas Turbine'] = ss['Gas Turbine'].sum() / solar_summary.loc['Solar','Energy'] #find resource mix for Gas Turbine
solar_summary.loc['Solar','Internal Combustion'] = ss['Internal Combustion'].sum() / solar_summary.loc['Solar','Energy'] #find resource mix for internal combustion
solar_summary.loc['Solar','Other Fossil'] = ss['Other Fossil'].sum() / solar_summary.loc['Solar','Energy'] #find resource mix for other fossil
solar_summary.loc['Solar','Other Peaker'] = ss['Other Peaker'].sum() / solar_summary.loc['Solar','Energy'] #find resource mix for other peaker
solar_summary.loc['Solar','Hydro'] = ss['Hydro'].sum() / solar_summary.loc['Solar','Energy'] #find resource mix for hydro
solar_summary.loc['Solar','Wind'] = ss['Wind'].sum() / solar_summary.loc['Solar','Energy'] #find resource mix for wind
solar_summary.loc['Solar','DR'] = ss['DR'].sum() / solar_summary.loc['Solar','Energy'] #find resource mix for DR
solar_summary.loc['Solar','Solar'] = ss['Solar'].sum() / solar_summary.loc['Solar','Energy'] #find resource mix for solar
solar_summary.rename(index={'Solar':'1.5 GW Solar'}, inplace=True)

#create summary stats comparing differences in scenarios
Delta = Delta.append(solar_summary) 

ss15 = dispatch('solar15', solar_sc=True, solarFile=solar15) #run dispatch function with solar data

solar_summary15 = pd.DataFrame(index=['Solar'],columns=['Energy','Cost','Emissions','Avg Ems Rate']) #create new dataframe
solar_summary15.loc['Solar','Energy'] = ss15['Demand'].sum() + ss15['Solar'].sum() #find total energy consumption
cost = ss15['Demand'] * ss15['MCE'] #find the cost of generation for each bid
solar_summary15.loc['Solar','Cost'] = cost.sum() #find the total cost of generation
solar_summary15.loc['Solar','Emissions'] = ss15['Total Ems'].sum() #find total emissions
solar_summary15.loc['Solar','Avg Ems Rate'] = solar_summary15.loc['Solar','Emissions'] / solar_summary15.loc['Solar','Energy'] #find average emissions rate
solar_summary15.loc['Solar','Steam Turbine'] = ss15['Steam Turbine'].sum() / solar_summary15.loc['Solar','Energy'] #find resource mix for steam turbine
solar_summary15.loc['Solar','Combined Cycle'] = ss15['Combined Cycle'].sum() / solar_summary15.loc['Solar','Energy'] #find resource mix for Combined Cycle
solar_summary15.loc['Solar','Gas Turbine'] = ss15['Gas Turbine'].sum() / solar_summary15.loc['Solar','Energy'] #find resource mix for Gas Turbine
solar_summary15.loc['Solar','Internal Combustion'] = ss15['Internal Combustion'].sum() / solar_summary15.loc['Solar','Energy'] #find resource mix for internal combustion
solar_summary15.loc['Solar','Other Fossil'] = ss15['Other Fossil'].sum() / solar_summary15.loc['Solar','Energy'] #find resource mix for other fossil
solar_summary15.loc['Solar','Other Peaker'] = ss15['Other Peaker'].sum() / solar_summary15.loc['Solar','Energy'] #find resource mix for other peaker
solar_summary15.loc['Solar','Hydro'] = ss15['Hydro'].sum() / solar_summary15.loc['Solar','Energy'] #find resource mix for hydro
solar_summary15.loc['Solar','Wind'] = ss15['Wind'].sum() / solar_summary15.loc['Solar','Energy'] #find resource mix for wind
solar_summary15.loc['Solar','DR'] = ss15['DR'].sum() / solar_summary15.loc['Solar','Energy'] #find resource mix for DR
solar_summary15.loc['Solar','Solar'] = ss15['Solar'].sum() / solar_summary15.loc['Solar','Energy'] #find resource mix for solar
solar_summary15.rename(index={'Solar':'15 GW Solar'}, inplace=True)

#create summary stats comparing differences in scenarios
Delta = Delta.append(solar_summary15) 
'''
if co2_price > 0: #if there was also a carbon scenario
        Delta.loc['Solar delta'] = Delta.iloc[4,:] - Delta.iloc[1,:]
else: #if there was only a solar scenario
        Delta.loc['Solar delta'] = Delta.iloc[2,:] - Delta.iloc[1,:]
        '''

for n in co2_price: #calculate carbon price scenario results
        carbon = dispatch('carbon', carbonPrice=n) #run dispatch function with carbon price

        carbon_summary = pd.DataFrame(index=['Carbon Price'],columns=['Energy','Cost','Emissions','Avg Ems Rate']) #create new dataframe
        carbon_summary.loc['Carbon Price','Energy'] = carbon['Demand'].sum() #find total energy consumption
        cost = carbon['Demand'] * carbon['MCE'] #find the cost of generation for each bid
        carbon_summary.loc['Carbon Price','Cost'] = cost.sum() #find the total cost of generation
        carbon_summary.loc['Carbon Price','Emissions'] = carbon['Total Ems'].sum() #find total emissions
        carbon_summary.loc['Carbon Price','Avg Ems Rate'] = carbon_summary.loc['Carbon Price','Emissions'] / carbon_summary.loc['Carbon Price','Energy'] #find average emissions rate
        carbon_summary.loc['Carbon Price','Steam Turbine'] = carbon['Steam Turbine'].sum() / carbon_summary.loc['Carbon Price','Energy'] #find resource mix for steam turbine
        carbon_summary.loc['Carbon Price','Combined Cycle'] = carbon['Combined Cycle'].sum() / carbon_summary.loc['Carbon Price','Energy'] #find resource mix for Combined Cycle
        carbon_summary.loc['Carbon Price','Gas Turbine'] = carbon['Gas Turbine'].sum() / carbon_summary.loc['Carbon Price','Energy'] #find resource mix for Gas Turbine
        carbon_summary.loc['Carbon Price','Internal Combustion'] = carbon['Internal Combustion'].sum() / carbon_summary.loc['Carbon Price','Energy'] #find resource mix for internal combustion
        carbon_summary.loc['Carbon Price','Other Fossil'] = carbon['Other Fossil'].sum() / carbon_summary.loc['Carbon Price','Energy'] #find resource mix for other fossil
        carbon_summary.loc['Carbon Price','Other Peaker'] = carbon['Other Peaker'].sum() / carbon_summary.loc['Carbon Price','Energy'] #find resource mix for other peaker
        carbon_summary.loc['Carbon Price','Hydro'] = carbon['Hydro'].sum() / carbon_summary.loc['Carbon Price','Energy'] #find resource mix for hydro
        carbon_summary.loc['Carbon Price','Wind'] = carbon['Wind'].sum() / carbon_summary.loc['Carbon Price','Energy'] #find resource mix for wind
        carbon_summary.loc['Carbon Price','DR'] = carbon['DR'].sum() / carbon_summary.loc['Carbon Price','Energy'] #find resource mix for DR
        carbon_summary.loc['Carbon Price','Solar'] = carbon['Solar'].sum() / carbon_summary.loc['Carbon Price','Energy'] #find resource mix for DR
        carbon_summary.rename(index={'Carbon Price':'Carbon Price '+str(n)}, inplace=True)

        #create summary stats comparing differences in scenarios
        Delta = Delta.append(carbon_summary) 
        #Delta.loc['Carbon delta'] = Delta.iloc[2,:] - Delta.iloc[1,:]




#Find the percent error between actual and baseline
Delta.loc['Baseline Error'] = (Delta.iloc[1,:] - Delta.iloc[0,:]) / Delta.iloc[0,:]

print('Exporting daily summary report...')
with open(Path.cwd() / ('outputs/day_summary.csv'),'w') as f:    #export summary report to csv file
        Delta.to_csv(f, header=True, index=True)

print('Done!')