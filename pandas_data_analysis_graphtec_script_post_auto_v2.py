from turtle import title
import numpy as np
import pandas as pd
import os
import time
import datetime
import re
from scipy import stats
import json


def graphtec_analysis(path, dir, experiment_list, dictionary):
    listings = []
    parent_directory = dir
    parent_path = os.path.join(path, parent_directory)

    def rounding(val):
        return(round(val,2))

    for expt_num, expt in enumerate(experiment_list, 1):
        listings = []
        volumes = []
        if expt["P_start"] > expt["P_end"]:
            expt_type = "vent"
            # conditions is a list of P_target values and P_target limits for data analysis containing: 
            # 1) the P_start point with a slight offset of 0.01 psig (can be removed; this is just the legacy process for the data analysis), 
            # 2) the P_end point with a slight offset of 0.01 psig, 
            # 3) the absolute difference between P_start and P_end as a limiting condition for correction variable used for P_start (lower limit) and P_end (upper limit), 
            # 4) the P_delay as an upper limiting condition for correction variable of P_start
            conditions = [expt["P_start"] + 0.01, expt["P_end"] +0.01, abs(expt["P_start"]-expt["P_end"]), expt["P_delay"]]
        else:
            # same conditions for vent except that the offset of 0.01 psig is subtracted instead of added
            expt_type = "fill"
            conditions = [expt["P_start"] - 0.01, expt["P_end"] -0.01, abs(expt["P_start"]-expt["P_end"]), expt["P_delay"]]
        for vol in dictionary["Volumes"]:
            results = dictionary[str(expt_num)][str(vol)]
            volume_listing= []
            volumes.append(float(vol))
            for result in results:
                file_info = []
                file_info.append(result[2])
                file_info.append(result[3])
                file_info.append(result[1])
                volume= float(result[0])
                file_info.append(volume)
                volume_listing.append(file_info)
            listings.append(volume_listing)

        def skip(num):
            if num<34 or num == 35:
                return True
            else:
                return False

        start_results=[]
        end_results=[]
        start_pressures = []
        end_pressures = []
        pressure_change_times = []
        average_pressure_change_times = []
        standard_deviation_pressure_change_times = []
        # very hack-y, but two sets of lists for averages and standard deviations, one that is just the values and another for the csv that includes empty strings for line breaks
        csv_average_pressure_change_times = []
        csv_standard_deviation_pressure_change_times = []
        collected_volume_time_results = []
        csv_volumes = []

        if expt_type == "fill":
            av_upstream_pressures = []
            sd_upstream_pressures = []


        for volume_section in listings:
            start_time_block = []
            end_time_block = []
            P_start_block = []
            P_end_block = []
            pressure_change_time_block = []
            # volume_block = []
            

            if expt_type == "fill":
                average_upstream_pressure_point = []
                sd_upstream_pressure_point = []
            
            def file_search_regex(regex, path):
                result = []
                for root, dirs, files in os.walk(path):
                    for name in files:
                        if re.match(regex, name):
                            result.append(os.path.join(root, name))
                return result
            
            # regex matches the YYMMDD-HHMMSS format of the Graphtec file
            file = file_search_regex("^\d{6}-\d{6}", parent_path)
            if len(file) == 0:
                raise Exception("Graphtec file not found. Please check the root of the experiment subdirectory for a raw data file matching 'YYMMDD-HHMMSS.csv' format and transfer the data file to this subdirectory from the Graphtec SD card, if necessary")                
            file = file[0]

            for expt_info in volume_section:
                print(f"analyzing experiment# {expt_num} with info in order of start timestamp, end timestamp, automation filepath for reference, and volume in L:",expt_info)


                data = pd.read_csv(file, skiprows = lambda x: skip(x), sep = ",")
                start_datetime_object = datetime.datetime.strptime(expt_info[0], '%Y-%m-%d %H:%M:%S.%f')
                end_datetime_object = datetime.datetime.strptime(expt_info[1], '%Y-%m-%d %H:%M:%S.%f')
                data['Date&Time'] = data['Date&Time'].apply(lambda x: datetime.datetime.strptime(x, '%Y/%m/%d %H:%M:%S'))

                data = data[(data["Date&Time"] >= start_datetime_object) & (data["Date&Time"] <= end_datetime_object)]

                data['Number']=data['Number'].apply(lambda x: x*0.2)
                data['Number']=data['Number']-data['Number'].iloc[0]
            
                data['CH2'] = data['CH2'].apply(lambda x: x[1:])
                data['CH2'] = data['CH2'].astype(float)

                if expt_type == "fill":
                    data['CH3'] = data['CH3'].apply(lambda x: x[1:])
                    data['CH3'] = data['CH3'].astype(float)

                start_point = data[data.CH2 == rounding(conditions[0])][:1]["Number"].to_numpy()
                correction = 0
                while len(start_point) == 0 and correction < conditions[3]:
                    if expt_type == "fill":
                        correction-= 0.01
                    else:
                        correction+= 0.01
                    start_point = data[data.CH2 == rounding(conditions[0]+correction)][:1]["Number"].to_numpy()
                if correction == conditions[3]: # logic to switch to checking condition[0], starting pressure, subtracting with the correction, instead of adding it
                    correction = 0
                    while len(start_point) == 0 and correction >conditions[2]:
                        if expt_type == "fill":
                            correction+= 0.01
                        else:
                            correction-= 0.01
                        start_point = data[data.CH2 == rounding(conditions[0]+correction)][:1]["Number"].to_numpy()
                    if correction == conditions[2]:
                        raise Exception('Start pressure not found. Recheck your analysis parameters (expt_list and results_dict) and experiment data')
                start_pressure = conditions[0]+correction

                start_time_block.append(start_point[0])
                P_start_block.append(start_pressure)
                end_point = data[data.CH2 == rounding(conditions[1])][:1]["Number"].to_numpy()
                correction = 0
                while len(end_point) == 0 and correction < conditions[2]:
                    correction+= 0.01
                    end_point = data[data.CH2 == rounding(conditions[1]+correction)][:1]["Number"].to_numpy()
                if correction == conditions[2]: # logic to switch to checking condition[1], ending pressure, subtracting with the correction, instead of adding it
                    correction = 0
                    while len(end_point) == 0 and correction <0.2: # lower limit set only to 0.2 psig, an arbitrary lower limit as the data collection should have stopped not too much lower than from P_end
                        correction+= 0.01
                        end_point = data[data.CH2 == rounding(conditions[1]+correction)][:1]["Number"].to_numpy()
                    if correction == 0.2:
                        raise Exception('End pressure not found. Recheck your analysis parameters (expt_list and results_dict) and experiment data')
                end_pressure = conditions[1]+correction
                
                end_time_block.append(end_point[0])
                P_end_block.append(end_pressure)
                pressure_change_time_block.append(end_point[0]-start_point[0])
                collected_volume_time_results.append([expt_info[-1], end_point[0]-start_point[0]])
                
                if expt_type == "fill":
                    data = data[(data["CH2"] >= start_pressure) & (data["CH2"] <= end_pressure)]
                    average_upstream_pressure_point.append(rounding(data["CH3"].mean()))
                    sd_upstream_pressure_point.append(rounding(data["CH3"].std()))


            start_results.append(start_time_block)
            end_results.append(end_time_block)
            
            start_pressures.append(P_start_block)
            end_pressures.append(P_end_block)
            


            average_pressure_change_times.append(sum(pressure_change_time_block)/len(pressure_change_time_block))
            csv_average_pressure_change_times.append([rounding(sum(pressure_change_time_block)/len(pressure_change_time_block))]+np.repeat("",expt["count"]-1).tolist())
            
            standard_deviation_pressure_change_times.append(np.std(pressure_change_time_block, ddof=1).tolist())
            csv_standard_deviation_pressure_change_times.append([rounding(np.std(pressure_change_time_block, ddof=1).tolist())]+np.repeat("",expt["count"]-1).tolist())
            
            pressure_change_times.append(pressure_change_time_block)
            csv_volumes.append([expt_info[3]]+np.repeat("",expt["count"]-1).tolist())
            
            if expt_type == "fill":
                av_upstream_pressures.append(average_upstream_pressure_point)
                sd_upstream_pressures.append(sd_upstream_pressure_point)

        time_array = np.array(average_pressure_change_times, dtype=np.float64)
        vol_array = np.array(volumes, dtype=np.float64)
        time_volume_calibration = stats.linregress(time_array, vol_array)
        def calculated_volume(xval):
            return(time_volume_calibration.slope*xval + time_volume_calibration.intercept)
        calc_volumes = [(calculated_volume(x[1])) for x in collected_volume_time_results]
        abs_errors = [(abs(calc_volumes[x]-collected_volume_time_results[x][0])) for x in range(0,len(collected_volume_time_results))]
        abs_errors_squared = [(x**2) for x in abs_errors]

        csv_standard_deviation_volumes = []
        for block in csv_standard_deviation_pressure_change_times:
            volume_block = []
            for sd in block:
                if sd == '':
                    volume_block.append(sd)
                else:
                    volume_block.append(rounding(sd*-time_volume_calibration.slope))
            csv_standard_deviation_volumes.append(volume_block)

        local_rmsds = []
        local_rmsds_block = []
        summation = 0
        for val_index,val in enumerate(abs_errors_squared,1):
            if (val_index % expt["count"]== 0):
                summation += val
                local_rmsds_block.insert(0, rounding((summation/(expt["count"]-1))**0.5))
                local_rmsds.append(local_rmsds_block)
                local_rmsds_block = []
                summation=0
            else:
                local_rmsds_block.append("")
                summation += val

        global_rmsd = [rounding((sum(abs_errors_squared)/(len(abs_errors_squared)-1))**0.5)] +np.repeat("",len(abs_errors_squared)-1).tolist()
        slope = [rounding(time_volume_calibration.slope)] +np.repeat("",len(abs_errors_squared)-1).tolist()
        intercept = [rounding(time_volume_calibration.intercept)] +np.repeat("",len(abs_errors_squared)-1).tolist()


        df_list = []
        if expt_type == "vent":
            units_dataframe = {"files": ["name"],"tank fill volume": ["L"], "P_start": ["psig"], "P_end": ["psig"], "start time": ["s"], "end time": ["s"], "pressure change time": ["s"], "volume": ["L"], "average pressure change time": ["s"], "std. dev. change time": ["s"], "std. dev. volume" : ["L"], "calculated volume": ["L"], "absolute error": ["L"], "absolute error^2": ["L^2"], "Tank Fill Volume": ["L"], "local RMSD": ["L"], "global RMSD": ["L"], "slope": ["L/s"], "intercept": ["L"]}
        else:
            units_dataframe = {"files": ["name"],"tank fill volume": ["L"], "P_start": ["psig"], "P_end": ["psig"], "ave. upstream pressure": ["psig"], "st. dev. upstream pressure": ["psig"],"start time": ["s"], "end time": ["s"], "pressure change time": ["s"], "volume": ["L"], "average pressure change time": ["s"], "std. dev. change time": ["s"], "std. dev. volume" : ["L"], "calculated volume": ["L"], "absolute error": ["L"], "absolute error^2": ["L^2"], "Tank Fill Volume": ["L"], "local RMSD": ["L"], "global RMSD": ["L"], "slope": ["L/s"], "intercept": ["L"]}
        
        total_index = 0
        df_list.append(pd.DataFrame(data=units_dataframe))
        for index, volume_section in enumerate(listings,0):
            for idx, expt_info in enumerate(volume_section, 0):
                if expt_type == "vent":
                    inputs = {"files": expt_info[2], "tank fill volume": expt_info[3], "P_start": start_pressures[index][idx], "P_end": end_pressures[index][idx], "start time": start_results[index][idx], "end time": end_results[index][idx], "pressure change time": pressure_change_times[index][idx], "volume": expt_info[3],"calculated volume": calc_volumes[total_index], "absolute error": abs_errors[total_index], "absolute error^2": abs_errors_squared[total_index],  "average pressure change time": csv_average_pressure_change_times[index][idx], "std. dev. change time": csv_standard_deviation_pressure_change_times[index][idx], "std. dev. volume" : csv_standard_deviation_volumes[index][idx], "Tank Fill Volume": expt_info[3],"local RMSD": local_rmsds[index][idx], "global RMSD": global_rmsd[total_index], "slope": slope[total_index], "intercept": intercept[total_index]}
                else:
                    inputs = {"files": expt_info[2], "tank fill volume": expt_info[3], "P_start": start_pressures[index][idx], "P_end": end_pressures[index][idx], "ave. upstream pressure": av_upstream_pressures[index][idx], "st. dev. upstream pressure": sd_upstream_pressures[index][idx],"start time": start_results[index][idx], "end time": end_results[index][idx], "pressure change time": pressure_change_times[index][idx], "volume": expt_info[3], "calculated volume": calc_volumes[total_index], "absolute error": abs_errors[total_index], "absolute error^2": abs_errors_squared[total_index],  "average pressure change time": csv_average_pressure_change_times[index][idx], "std. dev. change time": csv_standard_deviation_pressure_change_times[index][idx], "std. dev. volume" : csv_standard_deviation_volumes[index][idx], "Tank Fill Volume": expt_info[3], "local RMSD": local_rmsds[index][idx], "global RMSD": global_rmsd[total_index], "slope": slope[total_index], "intercept": intercept[total_index]}

                df = pd.DataFrame(data= [inputs])
                df_list.append(df)
                total_index+=1

        df = pd.concat(df_list)
        df.to_csv(f"{parent_path}/{dir} Graphtec Python analysis experiment#{expt_num}.csv", index=False) # update file path for writing
